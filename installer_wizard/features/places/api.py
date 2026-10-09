from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from access import NO_CACHE, require_admin

from features.places import inventory
from features.places.locate import locator
from features.places.store import store

admin_routes = APIRouter()


async def _body(request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Richiesta non valida")
    return body


def _overview() -> dict:
    from features.people import people
    located = locator.everyone()
    names = {p["slug"]: people.display_name(p) for p in people.all_profiles(light=True)} if located else {}
    return {**store.export(), "devices": inventory.devices(),
            "people": [{"slug": s, "name": names.get(s, s), **where} for s, where in located.items()]}


def _guard(action):
    try:
        action()
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return JSONResponse(_overview(), headers=NO_CACHE)


@admin_routes.get("/api/places")
async def admin_places(_: str = Depends(require_admin)):
    return JSONResponse(_overview(), headers=NO_CACHE)


@admin_routes.post("/api/places/floors")
async def admin_floor_add(request: Request, _: str = Depends(require_admin)):
    body = await _body(request)
    return _guard(lambda: store.put_floor(body))


@admin_routes.put("/api/places/floors/{fid}")
async def admin_floor_edit(fid: str, request: Request, _: str = Depends(require_admin)):
    body = await _body(request)
    if fid not in store.floors:
        raise HTTPException(404, "Piano sconosciuto")
    return _guard(lambda: store.put_floor(body, fid))


@admin_routes.delete("/api/places/floors/{fid}")
async def admin_floor_delete(fid: str, _: str = Depends(require_admin)):
    return _guard(lambda: store.delete_floor(fid))


@admin_routes.post("/api/places/rooms")
async def admin_room_add(request: Request, _: str = Depends(require_admin)):
    body = await _body(request)
    return _guard(lambda: store.put_room(body))


@admin_routes.put("/api/places/rooms/{rid}")
async def admin_room_edit(rid: str, request: Request, _: str = Depends(require_admin)):
    body = await _body(request)
    if rid not in store.rooms:
        raise HTTPException(404, "Stanza sconosciuta")
    return _guard(lambda: store.put_room(body, rid))


@admin_routes.delete("/api/places/rooms/{rid}")
async def admin_room_delete(rid: str, _: str = Depends(require_admin)):
    return _guard(lambda: store.delete_room(rid))


@admin_routes.put("/api/places/devices/{key:path}")
async def admin_place_device(key: str, request: Request, _: str = Depends(require_admin)):
    body = await _body(request)
    return _guard(lambda: store.place(key, str(body.get("room_id") or ""), list(body.get("senses") or [])))


@admin_routes.post("/api/places/import")
async def admin_import_home(_: str = Depends(require_admin)):
    from features.home_assistant.home import brain
    floors, areas = getattr(brain, "floors", {}) or {}, getattr(brain, "areas", {}) or {}
    if not areas:
        raise HTTPException(409, "Nessuna area da importare: collega prima Home Assistant")
    added = store.import_areas(floors, areas)
    return {"added": added, **_overview()}
