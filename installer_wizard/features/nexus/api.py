import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

import setup_api
from access import NO_CACHE, require_admin
from config import PUBLIC_PORT

from features.nexus import page
from features.nexus.application.tool_service import ToolNotFound
from features.nexus.composition import feature_folders, freshness, preferences, summary, tools

admin_routes = APIRouter()
MAX_BODY = 4096


async def _refresh_badges() -> None:
    if freshness.due():
        await asyncio.to_thread(freshness.refresh, feature_folders())


async def _json_body(request: Request) -> dict:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "Richiesta troppo grande")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "JSON non valido")
    if not isinstance(body, dict):
        raise HTTPException(400, "Atteso un oggetto JSON")
    return body


@admin_routes.get("/nexus")
async def nexus_index(request: Request):
    if not setup_api.done():
        port = "" if PUBLIC_PORT == 80 else f":{PUBLIC_PORT}"
        return RedirectResponse(f"http://{request.url.hostname}{port}/setup", status_code=303)
    return page.render(request.url.scheme == "https")


@admin_routes.get("/api/nexus/preferences")
async def nexus_preferences(user: str = Depends(require_admin)):
    return JSONResponse(preferences.get(user).as_dict(), headers=NO_CACHE)


@admin_routes.put("/api/nexus/preferences")
async def nexus_preferences_update(request: Request, user: str = Depends(require_admin)):
    body = await _json_body(request)
    try:
        updated = preferences.update(user, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return JSONResponse(updated.as_dict(), headers=NO_CACHE)


@admin_routes.get("/api/nexus/summary")
async def nexus_summary(_: str = Depends(require_admin)):
    await _refresh_badges()
    return JSONResponse(summary.build(), headers=NO_CACHE)


@admin_routes.get("/api/nexus/tools/{fid}")
async def nexus_tool(fid: str, _: str = Depends(require_admin)):
    await _refresh_badges()
    try:
        return JSONResponse(tools.detail(fid), headers=NO_CACHE)
    except ToolNotFound:
        raise HTTPException(404, "Strumento sconosciuto")
