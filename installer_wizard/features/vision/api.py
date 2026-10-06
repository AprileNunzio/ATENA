import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from access import require_admin, require_display
from features.people import people
from features.people.api import sync_person_neuron
from features.vision import ir_auto, ir_configure, ir_emitter, stills
from features.vision.webcams import webcams
from features.vision.proxy import vision_proxy, vision_stream
from state import store
from tasks import background

FACES = Path(os.environ.get("ATENA_FACES_DIR", "/var/lib/atena/faces"))
public_routes = APIRouter()
admin_routes = APIRouter()


@public_routes.get("/api/vision/snapshot.jpg")
async def public_snapshot(request: Request):
    require_display(request)
    return await vision_proxy("/snapshot.jpg")


@public_routes.get("/api/vision/still/{sid}.jpg")
async def public_still(sid: str, request: Request):
    require_display(request)
    data = stills.get(sid) if re.fullmatch(r"[0-9a-f]{16}", sid) else None
    if not data:
        raise HTTPException(404, "Immagine non più disponibile")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})


@public_routes.get("/api/vision/live.mjpg")
async def public_live(request: Request):
    require_display(request)
    return await vision_stream("/live.mjpg")


@public_routes.get("/api/vision/hands.mjpg")
async def public_hands(request: Request):
    require_display(request)
    return await vision_stream("/hands.mjpg")


@admin_routes.get("/api/vision/snapshot.jpg")
async def admin_snapshot(_: str = Depends(require_admin)):
    return await vision_proxy("/snapshot.jpg")


@admin_routes.get("/api/vision/stream.mjpg")
async def admin_vision_stream(_: str = Depends(require_admin)):
    return await vision_stream()


@admin_routes.get("/api/vision/people")
async def admin_people(_: str = Depends(require_admin)):
    return await vision_proxy("/people")


@admin_routes.get("/api/vision/people/{slug}/photo.jpg")
async def admin_person_photo(slug: str, _: str = Depends(require_admin)):
    clean = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:40]
    path = FACES / clean / "photo.jpg"
    if clean and path.is_file():
        try:
            return Response(path.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
        except OSError:
            pass
    return await vision_proxy(f"/people/{clean or 'persona'}/photo.jpg")


@admin_routes.post("/api/vision/people")
async def admin_enroll(request: Request, user: str = Depends(require_admin)):
    name = str((await request.json()).get("name", "")).strip()
    resp = await vision_proxy("/people", "POST", {"name": name}, timeout=30)
    if resp.status_code == 200:
        slug = json.loads(resp.body)["slug"]
        people.ensure(slug, name)
        background(sync_person_neuron(slug))
        store.event("INFO", f"Volto registrato per '{name}' da {user}", "vision")
    return resp


@admin_routes.delete("/api/vision/people/{slug}")
async def admin_forget(slug: str, user: str = Depends(require_admin)):
    resp = await vision_proxy(f"/people/{slug}", "DELETE")
    if resp.status_code == 200:
        store.event("INFO", f"Volto eliminato: {slug} (da {user})", "vision")
    return resp


VOICE_REPORT = Path(os.environ.get("ATENA_VOICEPRINTS", "/var/lib/atena/voiceprints")) / "report.json"


def _voice_report() -> dict:
    try:
        return json.loads(VOICE_REPORT.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {}


@admin_routes.get("/api/vision/biometrics")
async def admin_biometrics(_: str = Depends(require_admin)):
    faces = []
    try:
        resp = await vision_proxy("/people/health")
        if resp.status_code == 200:
            faces = json.loads(resp.body).get("people", [])
    except HTTPException:
        faces = []
    voices = _voice_report().get("people", {})
    names = {f["slug"]: f["name"] for f in faces}
    rows = {f["slug"]: {"slug": f["slug"], "name": f["name"], "face": f, "voice": voices.get(f["slug"])} for f in faces}
    for slug, voice in voices.items():
        rows.setdefault(slug, {"slug": slug, "name": names.get(slug, slug), "face": None, "voice": voice})
    for row in rows.values():
        for entry in (row["voice"] or {}).get("similar", []):
            entry["name"] = names.get(entry["slug"], entry["slug"])
    return {"people": sorted(rows.values(), key=lambda r: r["name"].lower()),
            "voice_twin_similarity": _voice_report().get("twin_similarity")}


@admin_routes.get("/api/vision/ir.jpg")
async def admin_ir_frame(_: str = Depends(require_admin)):
    return await vision_proxy("/ir.jpg")


def _emitter_view() -> dict:
    selected = webcams.state.get("selected") or {}
    return ir_emitter.status(selected.get("ir"), selected.get("ir_mode"))


@admin_routes.get("/api/vision/webcams")
async def admin_webcams(_: str = Depends(require_admin)):
    return {**webcams.view(), "emitter": _emitter_view()}


@admin_routes.post("/api/vision/webcams/rescan")
async def admin_webcams_rescan(user: str = Depends(require_admin)):
    state = await webcams.refresh(force=True)
    store.event("INFO", f"Webcam riesaminate da {user}: {len(state.get('devices', []))} trovate", "vision")
    return {**webcams.view(), "emitter": _emitter_view()}


@admin_routes.post("/api/vision/webcams/ir/install")
async def admin_ir_install(request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    if body.get("confirm") is not True:
        raise HTTPException(400, "Serve la conferma esplicita: la configurazione modifica i comandi della webcam")
    try:
        await ir_emitter.install()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Download non riuscito: {exc}")
    store.event("INFO", f"Strumento emettitore infrarosso installato da {user}", "vision")
    return _emitter_view()


@admin_routes.post("/api/vision/webcams/ir/enable")
async def admin_ir_enable(user: str = Depends(require_admin)):
    try:
        await ir_emitter.enable_service()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    store.event("INFO", f"Emettitore infrarosso attivato all'avvio da {user}", "vision")
    return _emitter_view()


@admin_routes.post("/api/vision/webcams/ir/configure")
async def admin_ir_configure(request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    if body.get("confirm") is not True:
        raise HTTPException(400, "Serve la conferma esplicita: la configurazione prova i comandi della webcam")
    tool = ir_emitter.tool_path()
    if not tool:
        raise HTTPException(409, "Prima va installato lo strumento")
    selected = webcams.state.get("selected") or {}
    try:
        await ir_configure.start(tool, selected.get("ir") or "", selected.get("ir_mode"), ir_emitter.enable_service)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    store.event("INFO", f"Configurazione emettitore infrarosso avviata da {user}", "vision")
    return _emitter_view()


@admin_routes.post("/api/vision/webcams/ir/configure/answer")
async def admin_ir_answer(request: Request, _: str = Depends(require_admin)):
    choice = str((await request.json()).get("answer") or "")
    try:
        ir_configure.answer(choice)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return _emitter_view()


@admin_routes.post("/api/vision/webcams/ir/configure/cancel")
async def admin_ir_cancel(_: str = Depends(require_admin)):
    ir_auto.cancel()
    return _emitter_view()


@admin_routes.post("/api/vision/webcams/ir/auto")
async def admin_ir_auto(request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    if body.get("confirm") is not True:
        raise HTTPException(400, "Serve la conferma esplicita: la configurazione prova i comandi della webcam")
    try:
        ir_auto.start()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    store.event("INFO", f"Configurazione automatica dell'infrarosso avviata da {user}", "vision")
    return _emitter_view()
