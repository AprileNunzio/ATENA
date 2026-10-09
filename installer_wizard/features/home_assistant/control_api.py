from access import require_admin
from fastapi import APIRouter, Depends, HTTPException, Request

from features.home_assistant import home
from features.home_assistant.constants import LLM_DATA_KEYS
from features.home_assistant.nlu.calls import is_sensitive

admin_routes = APIRouter()
_ATTRS = ("brightness", "current_position", "temperature", "current_temperature", "unit_of_measurement",
          "device_class", "volume_level", "media_title", "hvac_modes", "supported_color_modes")


@admin_routes.get("/api/home/entities")
async def ha_entities(_: str = Depends(require_admin)):
    brain = home.brain
    rows = []
    for e in brain.entities.values():
        if e.get("disabled") or e["entity_id"] not in brain.states:
            continue
        st = brain.states[e["entity_id"]]
        attrs = st.get("attrs") or {}
        rows.append({"entity_id": e["entity_id"], "name": e["name"], "domain": e["domain"], "area_id": e.get("area_id"),
                     "state": st.get("state"), "controllable": bool(e.get("controllable")), "hidden": bool(e.get("hidden")),
                     "category": e.get("category") or "", "attrs": {k: attrs[k] for k in _ATTRS if k in attrs}})
    areas = [{"area_id": a["area_id"], "name": a["name"], "floor_id": a.get("floor_id")} for a in brain.areas.values()]
    floors = [{"floor_id": f["floor_id"], "name": f["name"], "level": f.get("level")} for f in brain.floors.values()]
    return {"entities": rows, "areas": areas, "floors": floors, "services": brain.services}


@admin_routes.post("/api/home/control")
async def ha_control(request: Request, user: str = Depends(require_admin)):
    brain, body = home.brain, await request.json()
    eid, service = str(body.get("entity_id", "")), str(body.get("service", ""))
    entity = brain.entities.get(eid)
    if not entity or not entity.get("controllable"):
        raise HTTPException(404, "Dispositivo non comandabile")
    if service not in brain.services.get(entity["domain"], []):
        raise HTTPException(400, "Comando non disponibile per questo dispositivo")
    data = {k: v for k, v in (body.get("data") or {}).items()
            if k in LLM_DATA_KEYS and isinstance(v, (int, float, str, bool, list))}
    if is_sensitive(entity["domain"], service, entity) and body.get("confirm") is not True:
        raise HTTPException(428, "Comando delicato: conferma per procedere")
    plan = {"kind": "command", "action": "panel", "how": "pannello", "sensitive": False,
            "calls": [{"domain": entity["domain"], "service": service, "entity_ids": [eid], "data": data}],
            "entities": [eid]}
    result = await brain.execute(plan, f"{service} {entity['name']}", f"pannello ({user})")
    if not result["ok"]:
        raise HTTPException(502, "; ".join(result["errors"])[:300] or "Comando non riuscito")
    return {"ok": True, "state": (brain.states.get(eid) or {}).get("state"), "ms": result["ms"]}
