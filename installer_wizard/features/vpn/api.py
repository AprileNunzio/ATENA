from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from access import NO_CACHE, require_admin
from state import store as system_store

from features.vpn import profiles, runner, wireguard
from features.vpn.service import service
from features.vpn.store import store

admin_routes = APIRouter()
LAN_ROUTES = ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"]


async def _body(request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Richiesta non valida")
    return body


def _profile(pid: str):
    try:
        return store.get(pid)
    except KeyError:
        raise HTTPException(404, "Profilo VPN sconosciuto")


def _overview() -> dict:
    with store.lock:
        rows = [profiles.describe(p, store.secrets(p.id)) | {"wanted": store.wanted.get(p.id, False),
                                                              "status": service.state.get(p.id, {"connected": False})}
                for p in store.profiles.values()]
    return {"profiles": rows, "tools": runner.available(), "guard_error": service.guard_error}


@admin_routes.get("/api/vpn")
async def admin_vpn(_: str = Depends(require_admin)):
    return JSONResponse(_overview(), headers=NO_CACHE)


@admin_routes.post("/api/vpn/profiles")
async def admin_vpn_create(request: Request, user: str = Depends(require_admin)):
    try:
        profile, secrets = profiles.build(await _body(request))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc).strip("'"))
    with store.lock:
        store.put_secrets(profile.id, secrets)
        store.profiles[profile.id] = profile
        store.wanted[profile.id] = False
        store.save()
    system_store.event("INFO", f"VPN: profilo «{profile.name}» ({profile.kind}) creato da {user}", "vpn")
    return _overview() | {"created": profiles.describe(profile, secrets)}


@admin_routes.put("/api/vpn/profiles/{pid}")
async def admin_vpn_update(pid: str, request: Request, user: str = Depends(require_admin)):
    current = _profile(pid)
    body = await _body(request)
    try:
        updated = profiles.update(current, body)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc).strip("'"))
    with store.lock:
        store.profiles[pid] = updated
        if isinstance(body.get("secrets"), dict):
            secrets = store.secrets(pid)
            for key in ("password", "secret", "auth_key", "username"):
                if body["secrets"].get(key):
                    secrets[key] = profiles.text_value(body["secrets"][key])
            store.put_secrets(pid, secrets)
        store.save()
    if store.wanted.get(pid):
        await service.disconnect(pid)
        await service.connect(pid)
    return _overview()


@admin_routes.delete("/api/vpn/profiles/{pid}")
async def admin_vpn_delete(pid: str, user: str = Depends(require_admin)):
    p = _profile(pid)
    if store.wanted.get(pid):
        await service.disconnect(pid)
    runner.wipe(p)
    with store.lock:
        store.profiles.pop(pid, None)
        store.wanted.pop(pid, None)
        store.drop_secrets(pid)
        store.save()
    system_store.event("INFO", f"VPN: profilo «{p.name}» eliminato da {user}", "vpn")
    return _overview()


@admin_routes.post("/api/vpn/profiles/{pid}/connect")
async def admin_vpn_connect(pid: str, _: str = Depends(require_admin)):
    _profile(pid)
    return {"status": await service.connect(pid), **_overview()}


@admin_routes.post("/api/vpn/profiles/{pid}/disconnect")
async def admin_vpn_disconnect(pid: str, _: str = Depends(require_admin)):
    _profile(pid)
    return {"status": await service.disconnect(pid), **_overview()}


def _server(pid: str):
    p = _profile(pid)
    if p.kind != "wireguard" or p.role != "server":
        raise HTTPException(400, "Il profilo non è un server WireGuard")
    return p


@admin_routes.post("/api/vpn/profiles/{pid}/peers")
async def admin_vpn_add_peer(pid: str, request: Request, user: str = Depends(require_admin)):
    p = _server(pid)
    body = await _body(request)
    with store.lock:
        try:
            peer, peer_secret = wireguard.add_peer(p.settings, str(body.get("name") or ""))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        secrets = store.secrets(pid)
        secrets.setdefault("peers", {})[peer["id"]] = peer_secret
        store.put_secrets(pid, secrets)
        store.save()
    system_store.event("INFO", f"VPN: dispositivo «{peer['name']}» aggiunto al server «{p.name}» da {user}", "vpn")
    if store.wanted.get(pid):
        await service.disconnect(pid)
        await service.connect(pid)
    return {"peer": peer, "config": _peer_config(p, peer["id"])}


def _peer_config(p, peer_id: str) -> str:
    secrets = store.secrets(p.id)
    peer = next((x for x in p.settings["peers"] if x["id"] == peer_id), None)
    if peer is None or peer_id not in secrets.get("peers", {}):
        raise HTTPException(404, "Dispositivo sconosciuto")
    return wireguard.render_peer(p, profiles.public_key(secrets), peer, secrets["peers"][peer_id], LAN_ROUTES)


@admin_routes.get("/api/vpn/profiles/{pid}/peers/{peer_id}")
async def admin_vpn_peer_config(pid: str, peer_id: str, _: str = Depends(require_admin)):
    return JSONResponse({"config": _peer_config(_server(pid), peer_id)}, headers=NO_CACHE)


@admin_routes.delete("/api/vpn/profiles/{pid}/peers/{peer_id}")
async def admin_vpn_remove_peer(pid: str, peer_id: str, user: str = Depends(require_admin)):
    p = _server(pid)
    with store.lock:
        p.settings["peers"] = [x for x in p.settings["peers"] if x["id"] != peer_id]
        secrets = store.secrets(pid)
        secrets.get("peers", {}).pop(peer_id, None)
        store.put_secrets(pid, secrets)
        store.save()
    if store.wanted.get(pid):
        await service.disconnect(pid)
        await service.connect(pid)
    return _overview()
