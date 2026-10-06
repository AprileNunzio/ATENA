from fastapi import APIRouter, Depends, HTTPException, Request

from access import require_admin

from features.printers.service import PrinterError, printers

admin_routes = APIRouter()
public_routes = APIRouter()


async def _body(request: Request) -> dict:
    if int(request.headers.get("content-length") or 0) > 8192:
        raise HTTPException(413, "printers.error.too_large")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "printers.error.body")
    return body


@admin_routes.get("/api/printers/list")
async def get_printers(_: str = Depends(require_admin)):
    return {"printers": printers.listing(), "default": printers.default_id, "can_install": printers.can_install()}


@admin_routes.post("/api/printers/add")
async def add_printer(request: Request, _: str = Depends(require_admin)):
    try:
        return {"ok": True, "printer": printers.add(await _body(request))}
    except PrinterError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.post("/api/printers/remove")
async def remove_printer(request: Request, _: str = Depends(require_admin)):
    try:
        return {"ok": printers.remove(str((await _body(request)).get("id") or ""))}
    except PrinterError as exc:
        raise HTTPException(400, str(exc))


@admin_routes.put("/api/printers/{pid}/options")
async def printer_options(pid: str, request: Request, _: str = Depends(require_admin)):
    try:
        return {"ok": True, "options": printers.set_options(pid, await _body(request))}
    except KeyError:
        raise HTTPException(404, "printers.error.unknown")


@admin_routes.post("/api/printers/{pid}/probe")
async def printer_probe(pid: str, _: str = Depends(require_admin)):
    try:
        return await printers.probe(pid)
    except KeyError:
        raise HTTPException(404, "printers.error.unknown")


@admin_routes.post("/api/printers/discover")
async def printer_discover(_: str = Depends(require_admin)):
    return await printers.discover()


@admin_routes.post("/api/printers/install")
async def printer_install(request: Request, _: str = Depends(require_admin)):
    import asyncio
    try:
        return {"ok": True, **(await asyncio.to_thread(printers.install, await _body(request)))}
    except PrinterError as exc:
        raise HTTPException(400, str(exc))
