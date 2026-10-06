from fastapi import APIRouter, Depends, HTTPException, Request

from access import require_admin

from features.twin.rules import RULES
from features.twin.service import twin

admin_routes = APIRouter()
public_routes = APIRouter()


@admin_routes.get("/api/twin")
async def twin_overview(_: str = Depends(require_admin)):
    return {"mode": twin.mode(), "rules": twin.config["rules"], "available": list(RULES), "history": twin.history}


@admin_routes.put("/api/twin/rules")
async def twin_rules(request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "twin.error.body")
    return {"rules": twin.set_rules(body)}


@admin_routes.post("/api/twin/simulate")
async def twin_simulate(request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    calls = body.get("calls") if isinstance(body, dict) else None
    if not isinstance(calls, list) or not 1 <= len(calls) <= 30:
        raise HTTPException(400, "twin.error.plan")
    plan = {"calls": []}
    for call in calls:
        try:
            domain, service = str(call["service"]).split(".", 1)
            entities = [str(e) for e in call["entity_ids"]][:50]
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, "twin.error.plan")
        plan["calls"].append({"domain": domain, "service": service, "entity_ids": entities,
                              "data": call.get("data") if isinstance(call.get("data"), dict) else {}})
    result = twin.check(plan)
    return {**result.to_dict(), "plan": result.plan}
