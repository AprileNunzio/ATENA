from fastapi import APIRouter, Depends, HTTPException, Request

from access import require_admin
from state import store

from features.authz import risk
from features.authz.policy import policy

admin_routes = APIRouter()


@admin_routes.get("/api/authz/policy")
async def admin_policy(_: str = Depends(require_admin)):
    return {"policy": policy.export(), "tools": {name: level.name.lower() for name, level in sorted(risk.TOOLS.items())},
            "connectors": {name: level.name.lower() for name, level in sorted(risk.CONNECTORS.items())}}


@admin_routes.put("/api/authz/policy")
async def admin_policy_update(request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Policy non valida")
    saved = policy.save(body)
    store.event("INFO", f"Policy delle autorizzazioni aggiornata da {user}", "authz")
    return {"policy": saved}
