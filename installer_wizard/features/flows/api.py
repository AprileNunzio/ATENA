import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from access import NO_CACHE, require_admin
from state import store

from features.flows.application.studio import ConfirmationRequired
from features.flows.composition import studio

admin_routes = APIRouter()
MAX_BODY = 16384


async def _body(request: Request) -> dict:
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


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@admin_routes.get("/api/flows/studio")
async def flows_studio(_: str = Depends(require_admin)):
    return JSONResponse(studio.studio(), headers=NO_CACHE)


@admin_routes.put("/api/flows/draft")
async def flows_draft(request: Request, _: str = Depends(require_admin)):
    try:
        return JSONResponse(studio.save_draft(await _body(request)), headers=NO_CACHE)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.delete("/api/flows/draft")
async def flows_discard(_: str = Depends(require_admin)):
    return JSONResponse(studio.discard_draft(), headers=NO_CACHE)


@admin_routes.post("/api/flows/publish")
async def flows_publish(request: Request, user: str = Depends(require_admin)):
    body = await _body(request)
    try:
        result = await studio.publish(user, body.get("password"), _ip(request))
    except ConfirmationRequired as exc:
        store.event("WARN", f"Pubblicazione del flusso negata a {user}: password errata", "flows")
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    store.event("INFO", f"Flusso di ragionamento v{result['version']['version']} pubblicato da {user}", "flows")
    return JSONResponse(result, headers=NO_CACHE)


@admin_routes.post("/api/flows/rollback/{number}")
async def flows_rollback(number: int, request: Request, user: str = Depends(require_admin)):
    body = await _body(request)
    try:
        result = await studio.rollback(number, user, body.get("password"), _ip(request))
    except ConfirmationRequired as exc:
        raise HTTPException(403, str(exc))
    except LookupError:
        raise HTTPException(404, "Versione del flusso inesistente")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    store.event("INFO", f"Flusso di ragionamento riportato alla versione {number} da {user}", "flows")
    return JSONResponse(result, headers=NO_CACHE)
