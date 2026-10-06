import asyncio
import base64
import binascii

from fastapi import APIRouter, HTTPException, Request, Response

from access import require_display
from features.whiteboard import service, teacher
from features.whiteboard.board import MAX_SNAPSHOT, board
from features.whiteboard.pdf_exporter import export_pages_to_pdf
from features.whiteboard.printer import printer_manager

public_routes = APIRouter()
admin_routes = APIRouter()
MAX_BODY = 3_000_000

async def body_of(request: Request) -> dict:
    require_display(request, "Solo dal display o dal pannello")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "Richiesta troppo grande")
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(400, "Richiesta non valida")
    return data if isinstance(data, dict) else {}

@public_routes.get("/api/board")
async def read(request: Request, rev: int = 0):
    require_display(request, "Solo dal display o dal pannello")
    if rev == board.rev:
        return {"rev": board.rev, "same": True}
    return board.view()

@public_routes.post("/api/board/stroke")
async def stroke(request: Request):
    data = await body_of(request)
    try:
        board.stroke(data.get("points"), data.get("color"), data.get("width"), data.get("tool") == "eraser")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    service.auto_solve_board()
    return {"rev": board.rev}

@public_routes.post("/api/board/text")
async def text(request: Request):
    data = await body_of(request)
    try:
        board.text(data.get("text", ""), data.get("x"), data.get("y"), data.get("size", 40), data.get("color", ""), "user")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    service.auto_solve_board()
    return {"rev": board.rev}

@public_routes.post("/api/board/undo")
async def undo(request: Request):
    await body_of(request)
    return {"undone": board.undo("user"), "rev": board.rev}

@public_routes.post("/api/board/clear")
async def clear(request: Request):
    await body_of(request)
    return {"cleared": board.clear(), "rev": board.rev}

@public_routes.post("/api/board/snapshot")
async def snapshot(request: Request):
    data = await body_of(request)
    raw = str(data.get("image", ""))
    try:
        board.set_snapshot(base64.b64decode(raw.split(",", 1)[-1], validate=True))
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Immagine non valida")
    return {"ok": True, "limit": MAX_SNAPSHOT}

@public_routes.post("/api/board/solve")
async def solve(request: Request):
    data = await body_of(request)
    expr = data.get("expression", "")
    if expr:
        res = service.solve_on_board(expr)
        return {"rev": board.rev, "result": res}
    res = await service.collaborate_math()
    return {"rev": board.rev, "result": res}

@public_routes.post("/api/board/auto_evaluate")
async def auto_evaluate(request: Request):
    await body_of(request)
    res = teacher.auto_evaluate()
    return {"evaluated": bool(res), "result": res, "rev": board.rev}

@public_routes.post("/api/board/page/new")
async def page_new(request: Request):
    await body_of(request)
    idx = board.add_page()
    return {"page": idx, "pages": len(board.pages), "rev": board.rev}

@public_routes.post("/api/board/page/switch")
async def page_switch(request: Request):
    data = await body_of(request)
    target = int(data.get("page", 0))
    idx = board.switch_page(target)
    return {"page": idx, "pages": len(board.pages), "rev": board.rev}

@public_routes.post("/api/board/page/delete")
async def page_delete(request: Request):
    data = await body_of(request)
    target = data.get("page")
    idx = board.delete_page(int(target) if target is not None else None)
    return {"page": idx, "pages": len(board.pages), "rev": board.rev}

@public_routes.post("/api/board/ai/toggle")
async def ai_toggle(request: Request):
    data = await body_of(request)
    state = board.toggle_ai(data.get("enabled"))
    return {"ai_enabled": state, "rev": board.rev}

@public_routes.get("/api/board/list")
async def list_boards(request: Request):
    require_display(request, "Solo dal display o dal pannello")
    return {"boards": board.get_save_names()}

@public_routes.post("/api/board/save")
async def save_board(request: Request):
    data = await body_of(request)
    name = data.get("name", "")
    if name:
        board.save_as(name)
    return {"rev": board.rev}

@public_routes.post("/api/board/load")
async def load_board(request: Request):
    data = await body_of(request)
    name = data.get("name", "")
    if name:
        board.load_from(name)
    return {"rev": board.rev}

@public_routes.get("/api/board/pdf")
async def download_pdf(request: Request):
    require_display(request, "Solo dal display o dal pannello")
    pdf_bytes = export_pages_to_pdf(board.pages)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="lavagna_atena.pdf"'})

@public_routes.get("/api/board/printers")
async def list_printers(request: Request):
    require_display(request, "Solo dal display o dal pannello")
    from features.printers.service import printers
    return {"printers": printers.listing(), "default": printers.default_id}

@public_routes.post("/api/board/print")
async def print_whiteboard(request: Request):
    require_display(request, "Solo dal display o dal pannello")
    data = await body_of(request)
    from features.printers.service import clean_options, printers
    printer_id = str(data.get("printer_id") or printers.default_id or "pdf_export")
    saved = printers.options.get(printer_id, {})
    opts = clean_options({**saved, **(data.get("options") if isinstance(data.get("options"), dict) else {})})
    try:
        res = await asyncio.to_thread(printer_manager.print_job, printer_id, opts)
        return {"status": "ok", "job": res}
    except Exception as exc:
        raise HTTPException(400, str(exc))

import textwrap
@public_routes.post("/api/board/ask")
async def ask_atena(request: Request):
    data = await body_of(request)
    question = data.get("question", "")
    try:
        reply = await service.look(question)
        lines = textwrap.wrap(reply, width=70)
        service.write(lines, size=32)
        return {"reply": reply, "rev": board.rev}
    except Exception as exc:
        raise HTTPException(400, str(exc))
