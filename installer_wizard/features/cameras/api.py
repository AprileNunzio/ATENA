from fastapi import APIRouter, Depends, HTTPException, Request

from access import require_admin, require_display

from features.cameras import api_extra, live, options
from features.cameras.api_shared import source_of
from features.cameras.cameras import cameras

admin_routes = APIRouter()
public_routes = APIRouter()
admin_routes.include_router(api_extra.router)


def public_source(source_id: str) -> dict:
    source = source_of(source_id)
    if source["hidden"] or source["kind"] == "infrared":
        raise HTTPException(404, "Telecamera non trovata")
    return source


async def mjpeg(source_id: str, source: dict | None = None):
    try:
        return await live.stream(source or source_of(source_id))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


async def still(source_id: str, source: dict | None = None):
    response = await live.snapshot(source or source_of(source_id))
    if response is None:
        raise HTTPException(503, "Nessun fotogramma dalla telecamera")
    return response


@public_routes.get("/api/cameras/sources")
async def public_sources(request: Request):
    require_display(request)
    return {"sources": live.public(live.listing())}


@public_routes.get("/api/cameras/live/{source_id}.mjpg")
async def public_live(source_id: str, request: Request):
    require_display(request)
    return await mjpeg(source_id, public_source(source_id))


@public_routes.get("/api/cameras/live/{source_id}.jpg")
async def public_still(source_id: str, request: Request):
    require_display(request)
    return await still(source_id, public_source(source_id))


@admin_routes.get("/api/cameras/sources")
async def admin_sources(_: str = Depends(require_admin)):
    return {"sources": live.public(live.all_rows())}


@admin_routes.get("/api/cameras/live/{source_id}.mjpg")
async def admin_live(source_id: str, _: str = Depends(require_admin)):
    return await mjpeg(source_id)


@admin_routes.get("/api/cameras/live/{source_id}.jpg")
async def admin_still(source_id: str, _: str = Depends(require_admin)):
    return await still(source_id)


@admin_routes.get("/api/cameras")
async def admin_cameras(_: str = Depends(require_admin)):
    return cameras.listing()


@admin_routes.post("/api/cameras")
async def admin_cameras_add(request: Request, _: str = Depends(require_admin)):
    try:
        return cameras._safe(cameras.add(await request.json()))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.put("/api/cameras/{cid}")
async def admin_cameras_update(cid: str, request: Request, _: str = Depends(require_admin)):
    try:
        return cameras._safe(cameras.update(cid, await request.json()))
    except KeyError:
        raise HTTPException(404, "Telecamera sconosciuta")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.delete("/api/cameras/{cid}")
async def admin_cameras_delete(cid: str, _: str = Depends(require_admin)):
    try:
        cameras.delete(cid)
    except KeyError:
        raise HTTPException(404, "Telecamera sconosciuta")
    options.forget(f"c-{cid}")
    return {"ok": True}
