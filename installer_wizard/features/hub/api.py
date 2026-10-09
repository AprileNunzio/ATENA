from access import require_admin
from fastapi import APIRouter, Depends
from state import store

from features.brain.journey import journeys
from features.brain.trace import trace
from features.hub import model

admin_routes = APIRouter()
MAX_DESKS = 16


def _presence() -> dict:
    presence = store.presence if isinstance(store.presence, dict) else {}
    people = [{"name": str(p.get("name") or "")[:40], "known": bool(p.get("known"))} for p in presence.get("people", [])][:8]
    return {"status": presence.get("status", ""), "people": people}


def _health() -> dict:
    parts = store.components or {}
    down = [str(c.get("label", k))[:60] for k, c in parts.items() if isinstance(c, dict) and c.get("status") == "down"]
    return {"phase": store.phase, "down": down[:6], "total": len(parts)}


@admin_routes.get("/api/hub")
async def hub_snapshot(_: str = Depends(require_admin)):
    snap = trace.snapshot()
    active, summary = snap["active"], trace.summary()
    extra = [a["component"] for a in active if a.get("component") and a["component"] not in model.DESKS]
    desks = list(dict.fromkeys([*model.DESKS, *extra]))[:MAX_DESKS]
    flows = journeys.snapshot()["journeys"][:model.MAX_JOURNEYS]
    return {"seq": snap["seq"] + journeys.seq, "stations": model.stations(),
            "journeys": [model.journey_view(j) for j in flows], "desks": [model.desk_view(d, active, summary) for d in desks],
            "presence": _presence(), "health": _health()}
