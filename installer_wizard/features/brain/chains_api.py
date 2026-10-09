from access import require_admin
from config import write_env
from fastapi import APIRouter, Depends, HTTPException, Request
from feature_registry import registry
from state import store
from tasks import background

from features.brain import presets, scope, sources
from features.brain.brains import brains
from features.brain.residency import rebalance
from features.brain.roles import BY_ID as ROLE_BY_ID
from features.brain.roles import ROLES

admin_routes = APIRouter()


def _commit(updates: dict, user: str, what: str) -> None:
    if not updates:
        return
    write_env(updates)
    brains.invalidate()
    background(rebalance())
    store.event("INFO", f"Cervello aggiornato da {user}: {what}", "models")


@admin_routes.get("/api/brains/sources")
async def brain_sources(_: str = Depends(require_admin)):
    return await sources.catalog()


@admin_routes.get("/api/brains/presets")
async def brain_presets(_: str = Depends(require_admin)):
    return {"presets": [{"id": p.id, "icon": p.icon, "label": p.label, "hint": p.hint, "scope": p.scope}
                        for p in presets.PRESETS],
            "scopes": list(scope.SCOPES), "strategies": list(scope.STRATEGIES)}


@admin_routes.post("/api/brains/preset")
async def brain_apply_preset(request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    preset_id = str(body.get("preset", ""))
    wanted = body.get("roles") or [r.id for r in ROLES]
    if not isinstance(wanted, list) or not all(str(r) in ROLE_BY_ID for r in wanted):
        raise HTTPException(400, "Ruolo sconosciuto")
    cat = await sources.catalog()
    updates = {}
    try:
        for role_id in dict.fromkeys(str(r) for r in wanted):
            role = ROLE_BY_ID[role_id]
            order, scope_value = presets.plan(preset_id, role_id, cat)
            updates.update({role.env_key: ",".join(order), role.scope_key: scope_value,
                            role.strategy_key: scope.DEFAULT_STRATEGY, role.profile_key: preset_id})
    except presets.PresetError as exc:
        raise HTTPException(400, str(exc))
    _commit(updates, user, f"profilo {preset_id} per {', '.join(wanted)}")
    return await brains.overview(registry.hw)


@admin_routes.put("/api/brains/settings/{role_id}")
async def brain_role_settings(role_id: str, request: Request, user: str = Depends(require_admin)):
    role = ROLE_BY_ID.get(role_id)
    if not role:
        raise HTTPException(404, "Ruolo sconosciuto")
    body, updates = await request.json(), {}
    if "scope" in body:
        if body["scope"] not in scope.SCOPES:
            raise HTTPException(400, "Ambito non valido")
        updates[role.scope_key] = body["scope"]
    if "strategy" in body:
        if body["strategy"] not in scope.STRATEGIES:
            raise HTTPException(400, "Strategia non valida")
        updates[role.strategy_key] = body["strategy"]
    if updates:
        updates[role.profile_key] = "custom"
    _commit(updates, user, f"impostazioni di {role.label}")
    return await brains.overview(registry.hw)
