import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from access import is_local, require_admin, require_display, session_user
from config import PUBLIC_PORT
from features.music import conf, covers, layout, stream, tokens
from features.music.api_library import body
from features.music.db import db
from features.music.outputs import DEVICE_RE, outputs

admin_routes = APIRouter()
public_routes = APIRouter()


def base_of(request: Request) -> str:
    host = request.url.hostname or "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"
    return f"http://{host}" + ("" if PUBLIC_PORT == 80 else f":{PUBLIC_PORT}")


def allowed(request: Request, kind: str, ref, token: str) -> bool:
    return bool(token and tokens.verify(kind, ref, token)) or is_local(request) or bool(session_user(request))


@public_routes.get("/api/music/media/{track_id}")
async def media(track_id: int, request: Request, t: str = "", fmt: str = ""):
    if not allowed(request, "media", track_id, t):
        raise HTTPException(401, "Collegamento scaduto o non valido")
    found = db.row("SELECT path FROM tracks WHERE id=?", (track_id,))
    if not found:
        raise HTTPException(404, "Brano non trovato")
    return stream.serve(layout.root() / found["path"], request, fmt)


@public_routes.get("/api/music/art/{album_key}")
async def art(album_key: str, request: Request, t: str = "", size: int = 300):
    if not allowed(request, "art", album_key, t):
        raise HTTPException(401, "Collegamento scaduto o non valido")
    data = await asyncio.to_thread(covers.thumbnail, album_key[:24], size)
    if data is None:
        raise HTTPException(404, "Nessuna copertina")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@public_routes.get("/api/music/out/poll")
async def poll(request: Request, device: str = "", name: str = ""):
    require_display(request, "Solo dal display")
    if not DEVICE_RE.match(device) or not device.startswith("display:"):
        raise HTTPException(400, "Dispositivo non valido")
    if not conf.cast_enabled():
        return {"idle": 60}
    return {"command": await outputs.wait_command(device, name)}


@public_routes.post("/api/music/out/report")
async def report(request: Request):
    require_display(request, "Solo dal display")
    data = await body(request)
    device = str(data.get("device") or "")
    if not DEVICE_RE.match(device):
        raise HTTPException(400, "Dispositivo non valido")
    try:
        position = float(data.get("position") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "Posizione non valida")
    outputs.remote_report(device, str(data.get("state") or ""), position, bool(data.get("ended")))
    return {"ok": True}


def failure(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, "Dispositivo non trovato")
    if isinstance(exc, ValueError):
        return HTTPException(400, str(exc))
    return HTTPException(502, str(exc))


@admin_routes.get("/api/music/out")
async def listing(refresh: bool = False, _: str = Depends(require_admin)):
    return {"devices": await outputs.refresh(refresh), "cast": conf.cast_enabled()}


@admin_routes.get("/api/music/out/{device}")
async def state(device: str, _: str = Depends(require_admin)):
    session = outputs.sessions.get(device)
    return outputs.view(session) if session else {"device": device, "state": "stopped", "queue": [], "length": 0}


@admin_routes.post("/api/music/out/{device}/play")
async def play(device: str, request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    try:
        ids = [int(i) for i in (data.get("tracks") or [])]
        return await outputs.start(device, user, ids, int(data.get("index") or 0), float(data.get("start") or 0), base_of(request),
                                   str(data.get("repeat") or "off"))
    except (KeyError, ValueError, RuntimeError, TypeError) as exc:
        raise failure(exc)


@admin_routes.post("/api/music/out/{device}/control")
async def control(device: str, request: Request, _: str = Depends(require_admin)):
    data = await body(request)
    try:
        return await outputs.control(device, str(data.get("action") or ""), float(data.get("value") or 0), base_of(request))
    except (KeyError, ValueError, RuntimeError, TypeError) as exc:
        raise failure(exc)
