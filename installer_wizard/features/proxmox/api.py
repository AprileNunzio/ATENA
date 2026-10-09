from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from access import NO_CACHE, require_admin
from state import store

from features.proxmox.client import ProxmoxError, client, settings

admin_routes = APIRouter()


@admin_routes.get("/api/proxmox")
async def admin_proxmox(_: str = Depends(require_admin)):
    s = settings()
    if not s.host:
        return JSONResponse({"configured": False}, headers=NO_CACHE)
    try:
        data = await client.overview()
    except ProxmoxError as exc:
        return JSONResponse({"configured": True, "host": s.host, "error": str(exc)}, headers=NO_CACHE)
    return JSONResponse({"configured": True, "host": s.host, **data}, headers=NO_CACHE)


@admin_routes.post("/api/proxmox/{node}/{kind}/{vmid}/snapshot")
async def admin_proxmox_snapshot(node: str, kind: str, vmid: int, request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    try:
        task = await client.snapshot(node, kind, vmid, str((body or {}).get("name") or ""))
    except ProxmoxError as exc:
        raise HTTPException(400, str(exc))
    store.event("INFO", f"Proxmox: snapshot di {kind} {vmid} su {node} (da {user})", "proxmox")
    return {"task": task}


@admin_routes.post("/api/proxmox/{node}/{kind}/{vmid}/{action}")
async def admin_proxmox_power(node: str, kind: str, vmid: int, action: str, user: str = Depends(require_admin)):
    try:
        task = await client.power(node, kind, vmid, action)
    except ProxmoxError as exc:
        raise HTTPException(400, str(exc))
    store.event("INFO", f"Proxmox: {action} di {kind} {vmid} su {node} (da {user})", "proxmox")
    return {"task": task}
