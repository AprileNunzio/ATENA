from fastapi import APIRouter, Depends, HTTPException, Request

from access import require_admin

from features.nvr.service import nvr
from features.nvr.settings import SettingsError, public

admin_routes = APIRouter()
public_routes = APIRouter()


@admin_routes.get("/api/nvr/overview")
async def nvr_overview(_: str = Depends(require_admin)):
    return {**nvr.status(), "cameras": nvr.cameras()}


@admin_routes.get("/api/nvr/settings")
async def nvr_settings(_: str = Depends(require_admin)):
    return public(nvr.settings)


@admin_routes.put("/api/nvr/settings")
async def nvr_settings_update(request: Request, _: str = Depends(require_admin)):
    if int(request.headers.get("content-length") or 0) > 8192:
        raise HTTPException(413, "nvr.error.too_large")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "nvr.error.body")
    try:
        return nvr.update_settings(body)
    except SettingsError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.get("/api/nvr/search")
async def nvr_search(q: str = "", limit: int = 50, _: str = Depends(require_admin)):
    return nvr.search(q[:300], limit)


@admin_routes.delete("/api/nvr/events")
async def nvr_clear(_: str = Depends(require_admin)):
    nvr.store.clear()
    nvr.publish_status()
    return {"ok": True}
