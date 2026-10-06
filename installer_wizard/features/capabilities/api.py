import asyncio
import json
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from access import require_admin
from features.agent import registry
from features.agent.paths import level
from features.capabilities import audit, catalog, manifest, mcp, schema, tokens

public_routes = APIRouter()
admin_routes = APIRouter()
MAX_BODY = 256 * 1024
WATCH_EVERY = 3.0
KEEPALIVE = 15.0
MAX_STREAM = 3600.0
HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


@admin_routes.get("/api/capabilities")
async def capabilities(_: str = Depends(require_admin)):
    return manifest.document()


@admin_routes.get("/api/capabilities/schema/{flavor}")
async def tool_schemas(flavor: str, _: str = Depends(require_admin)):
    build = {"openai": schema.openai, "anthropic": schema.anthropic, "mcp": schema.definition}.get(flavor)
    if build is None:
        raise HTTPException(404, "Formato sconosciuto: openai, anthropic oppure mcp")
    return {"tools": [build(t["name"]) for t in registry.available(level())]}


@admin_routes.get("/api/mcp/tokens")
async def token_list(_: str = Depends(require_admin)):
    return {"tokens": tokens.listing()}


@admin_routes.post("/api/mcp/tokens")
async def token_create(request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    try:
        return tokens.create(str(body.get("label", "")), bool(body.get("risky")))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.delete("/api/mcp/tokens/{token_id}")
async def token_revoke(token_id: str, _: str = Depends(require_admin)):
    if not tokens.revoke(token_id):
        raise HTTPException(404, "Token sconosciuto")
    return {"ok": True}


@admin_routes.get("/api/mcp/audit")
async def calls(_: str = Depends(require_admin)):
    return {"calls": audit.recent()}


def authorize(request: Request) -> dict:
    origin = request.headers.get("Origin")
    if origin and urlparse(origin).netloc != request.headers.get("Host", ""):
        raise HTTPException(403, "Origine non consentita")
    token = tokens.check(request.headers.get("Authorization", ""), request.client.host if request.client else "")
    if token is None:
        raise HTTPException(401, "token mancante o non valido", headers={"WWW-Authenticate": "Bearer"})
    return token


async def changes(request: Request, token: dict):
    last = catalog.signature(mcp.visible(token))
    started = beat = time.time()
    yield ": atena\n\n"
    while time.time() - started < MAX_STREAM and not await request.is_disconnected():
        await asyncio.sleep(WATCH_EVERY)
        now = catalog.signature(mcp.visible(token))
        if now != last:
            last = now
            yield "data: " + json.dumps({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}) + "\n\n"
            beat = time.time()
        elif time.time() - beat > KEEPALIVE:
            beat = time.time()
            yield ": ping\n\n"


@admin_routes.get("/mcp")
async def mcp_stream(request: Request):
    token = authorize(request)
    return StreamingResponse(changes(request, token), media_type="text/event-stream", headers=HEADERS)


@admin_routes.post("/mcp")
async def mcp_endpoint(request: Request):
    token = authorize(request)
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "Richiesta troppo grande")
    try:
        body = json.loads(raw)
    except ValueError:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON non valido"}}, status_code=400)
    batch = body if isinstance(body, list) else [body]
    replies = [r for r in [await mcp.handle(m, token) for m in batch[:20]] if r is not None]
    if not replies:
        return Response(status_code=202)
    return JSONResponse(replies if isinstance(body, list) else replies[0])
