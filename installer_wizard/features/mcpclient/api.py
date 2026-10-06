from fastapi import APIRouter, Depends, HTTPException, Request

from access import require_admin
from features.mcpclient import service, store

public_routes = APIRouter()
admin_routes = APIRouter()


@admin_routes.get("/api/mcp/servers")
async def listing(_: str = Depends(require_admin)):
    return {"servers": [store.public(i, r) for i, r in store.load().items()], "enabled": service.enabled()}


@admin_routes.post("/api/mcp/servers")
async def add(request: Request, _: str = Depends(require_admin)):
    body = await request.json()
    try:
        server_id = store.add(body.get("name", ""), body.get("url", ""), body.get("token", ""), bool(body.get("trusted")))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    count = await service.sync_one(server_id)
    return {"id": server_id, "tools": count, "status": store.load()[server_id]["status"]}


@admin_routes.post("/api/mcp/servers/{server_id}/refresh")
async def refresh(server_id: str, _: str = Depends(require_admin)):
    if server_id not in store.load():
        raise HTTPException(404, "Server sconosciuto")
    count = await service.sync_one(server_id)
    return {"tools": count, "status": store.load()[server_id]["status"]}


@admin_routes.put("/api/mcp/servers/{server_id}")
async def change(server_id: str, request: Request, _: str = Depends(require_admin)):
    if server_id not in store.load():
        raise HTTPException(404, "Server sconosciuto")
    body = await request.json()
    fields = {k: bool(body[k]) for k in ("enabled", "trusted") if k in body}
    store.update(server_id, **fields)
    await service.sync_one(server_id)
    return {"ok": True}


@admin_routes.delete("/api/mcp/servers/{server_id}")
async def remove(server_id: str, _: str = Depends(require_admin)):
    if not store.remove(server_id):
        raise HTTPException(404, "Server sconosciuto")
    service.drop(server_id)
    return {"ok": True}
