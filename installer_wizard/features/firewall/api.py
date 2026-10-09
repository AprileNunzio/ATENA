import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from access import NO_CACHE, require_admin
from state import store as system_store

from features.firewall import model
from features.firewall.analyst import analyst
from features.firewall.applier import FirewallError, applier, render
from features.firewall.events import monitor
from features.firewall.nft import Block
from features.firewall.store import store

admin_routes = APIRouter()
CONFIRM_SECONDS = 90


async def _body(request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Richiesta non valida")
    return body


async def _change(user: str, reason: str, mutate, confirm: bool = True) -> dict:
    with store.lock:
        store.checkpoint(reason)
        try:
            mutate()
        except (KeyError, TypeError, ValueError) as exc:
            store.rollback()
            raise HTTPException(400, str(exc).strip("'"))
        store.save()
    system_store.event("INFO", f"Firewall · {reason} (da {user})", "firewall")
    try:
        outcome = await applier.apply(reason, CONFIRM_SECONDS if confirm else 0)
    except FirewallError as exc:
        store.rollback()
        try:
            await applier.apply("ripristino dopo errore")
        except FirewallError as again:
            system_store.event("ERROR", f"Firewall: ripristino non riuscito: {again}", "firewall")
        raise HTTPException(400, f"nftables ha rifiutato la modifica: {exc}")
    return {"applied": outcome, **store.snapshot()}


@admin_routes.get("/api/firewall")
async def admin_firewall(_: str = Depends(require_admin)):
    return JSONResponse({**store.snapshot(), "status": applier.status(), "engine": {"connected": monitor.connected},
                         "summary": monitor.summary, "alerts": list(monitor.alerts)[-50:],
                         "reports": list(analyst.reports)[-10:]}, headers=NO_CACHE)


@admin_routes.put("/api/firewall/policy")
async def admin_policy(request: Request, user: str = Depends(require_admin)):
    body = await _body(request)

    def mutate():
        store.policy = model.policy(body, store.policy)

    return await _change(user, f"politica aggiornata (modalità {body.get('mode', store.policy.mode)})", mutate)


@admin_routes.post("/api/firewall/rules")
async def admin_rule_create(request: Request, user: str = Depends(require_admin)):
    body = {**await _body(request), "id": ""}

    def mutate():
        rule = model.rule(body)
        store.rules[rule.id] = rule

    return await _change(user, f"nuova regola {body.get('action', '')} {body.get('comment', '')}".strip(), mutate)


@admin_routes.put("/api/firewall/rules/{rid}")
async def admin_rule_update(rid: str, request: Request, user: str = Depends(require_admin)):
    body = {**await _body(request), "id": rid}

    def mutate():
        if rid not in store.rules:
            raise KeyError("regola sconosciuta")
        store.rules[rid] = model.rule(body)

    return await _change(user, f"regola {rid} modificata", mutate)


@admin_routes.delete("/api/firewall/rules/{rid}")
async def admin_rule_delete(rid: str, user: str = Depends(require_admin)):
    def mutate():
        store.rules.pop(rid)

    return await _change(user, f"regola {rid} eliminata", mutate)


@admin_routes.put("/api/firewall/sets/{name}")
async def admin_set_update(name: str, request: Request, user: str = Depends(require_admin)):
    body = await _body(request)

    def mutate():
        store.sets[name] = model.address_set(name, body.get("entries") or [])

    return await _change(user, f"gruppo {name} aggiornato", mutate)


@admin_routes.delete("/api/firewall/sets/{name}")
async def admin_set_delete(name: str, user: str = Depends(require_admin)):
    def mutate():
        if any(a.family == "set" and a.value == name for r in store.rules.values() for a in r.sources + r.destinations):
            raise ValueError("il gruppo è usato da una regola")
        store.sets.pop(name)

    return await _change(user, f"gruppo {name} eliminato", mutate)


@admin_routes.post("/api/firewall/blocks")
async def admin_block(request: Request, user: str = Depends(require_admin)):
    body = await _body(request)
    minutes = max(0, min(int(body.get("minutes") or 0), 525_600))

    def mutate():
        address = model.address(str(body.get("address") or ""))
        if address.family == "set":
            raise ValueError("si può bloccare un indirizzo o un MAC, non un gruppo")
        expires = time.time() + minutes * 60 if minutes else 0.0
        store.blocks[address.value] = Block(address, expires, model.comment(body.get("reason") or "manuale"))

    return await _change(user, f"blocco di {body.get('address')}", mutate, confirm=False)


@admin_routes.delete("/api/firewall/blocks/{address:path}")
async def admin_unblock(address: str, user: str = Depends(require_admin)):
    def mutate():
        store.blocks.pop(model.address(address).value)

    return await _change(user, f"sblocco di {address}", mutate, confirm=False)


@admin_routes.get("/api/firewall/preview")
async def admin_preview(_: str = Depends(require_admin)):
    return {"script": render()}


@admin_routes.post("/api/firewall/confirm")
async def admin_confirm(user: str = Depends(require_admin)):
    confirmed = applier.confirm()
    if confirmed:
        system_store.event("INFO", f"Firewall: modifica confermata da {user}", "firewall")
    return {"confirmed": confirmed}


@admin_routes.post("/api/firewall/rollback")
async def admin_rollback(user: str = Depends(require_admin)):
    entry = store.rollback()
    if entry is None:
        raise HTTPException(404, "Nessuna configurazione precedente")
    applier.confirm()
    try:
        await applier.apply(f"ripristino richiesto da {user}")
    except FirewallError as exc:
        raise HTTPException(400, f"nftables ha rifiutato il ripristino: {exc}")
    return {"restored": entry["reason"], **store.snapshot()}


@admin_routes.post("/api/firewall/analyze")
async def admin_analyze(user: str = Depends(require_admin)):
    report = await analyst.analyse(f"richiesta di {user}")
    if report is None:
        raise HTTPException(409, "Analisi non disponibile: nessun dato recente, analisi già in corso o nessun modello")
    return report


@admin_routes.post("/api/firewall/reports/{rid}")
async def admin_report_decision(rid: str, request: Request, user: str = Depends(require_admin)):
    report = analyst.find(rid)
    if report is None:
        raise HTTPException(404, "Analisi sconosciuta")
    if report["status"] != "pending":
        raise HTTPException(409, "Analisi già gestita")
    body = await _body(request)
    if not body.get("approve"):
        report["status"] = f"rifiutato da {user}"
        return report
    chosen = body.get("actions")
    actions = [a for i, a in enumerate(report["actions"]) if not isinstance(chosen, list) or i in chosen]
    try:
        done = await analyst.apply(report, actions, user)
    except FirewallError as exc:
        raise HTTPException(400, f"nftables ha rifiutato la modifica: {exc}")
    return {**report, "done": done}
