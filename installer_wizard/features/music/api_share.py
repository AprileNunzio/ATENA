import asyncio
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from access import require_admin
from config import write_env
from features.music import conf, covers, layout, sharing, stream
from features.music.api_library import body
from features.music.api_play import base_of
from features.music.db import db

admin_routes = APIRouter()
public_routes = APIRouter()
PAGE = Path(__file__).resolve().parent / "share.html"
HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}


def client_of(request: Request) -> str:
    return request.client.host if request.client else "?"


def shared(token: str, request: Request) -> dict:
    client = client_of(request)
    if sharing.throttled(client):
        raise HTTPException(429, "Troppi tentativi: riprova tra un minuto")
    found = sharing.resolve(token)
    if not found:
        sharing.failed(client)
        raise HTTPException(404, "Collegamento scaduto o non valido")
    return found


@public_routes.get("/music/share/{token}")
async def page(token: str, request: Request):
    shared(token, request)
    return HTMLResponse(PAGE.read_text(encoding="utf-8"), headers=HEADERS)


@public_routes.get("/api/music/share/{token}/data")
async def data(token: str, request: Request):
    found = shared(token, request)
    sharing.touch(token)
    return {"title": found["title"], "kind": found["kind"], "expires": found["expires"], "tracks": found["tracks"]}


@public_routes.get("/api/music/share/{token}/media/{track_id}")
async def media(token: str, track_id: int, request: Request, fmt: str = ""):
    found = shared(token, request)
    if track_id not in {t["id"] for t in found["tracks"]}:
        raise HTTPException(404, "Brano non incluso")
    row = db.row("SELECT path FROM tracks WHERE id=?", (track_id,))
    if not row:
        raise HTTPException(404, "Brano non trovato")
    return stream.serve(layout.root() / row["path"], request, fmt)


@public_routes.get("/api/music/share/{token}/art/{album_key}")
async def art(token: str, album_key: str, request: Request):
    found = shared(token, request)
    if album_key not in {t["album_key"] for t in found["tracks"]}:
        raise HTTPException(404, "Copertina non inclusa")
    image = await asyncio.to_thread(covers.thumbnail, album_key[:24], 300)
    if image is None:
        raise HTTPException(404, "Nessuna copertina")
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@admin_routes.get("/api/music/shares")
async def listing(request: Request, user: str = Depends(require_admin)):
    return {"shares": sharing.listing(user), "base": base_of(request)}


@admin_routes.post("/api/music/shares")
async def create(request: Request, user: str = Depends(require_admin)):
    payload = await body(request)
    try:
        made = sharing.create(user, str(payload.get("kind") or ""), str(payload.get("ref") or ""), payload.get("hours"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc))
    return {**made, "url": f"{base_of(request)}/music/share/{made['token']}"}


@admin_routes.post("/api/music/shares/{token}/revoke")
async def revoke(token: str, user: str = Depends(require_admin)):
    if not sharing.revoke(user, token):
        raise HTTPException(404, "Collegamento non trovato")
    return {"ok": True}


def app_view(request: Request) -> dict:
    return {"enabled": conf.subsonic_enabled(), "password": conf.app_password() if conf.subsonic_enabled() else "", "has_password": len(conf.app_password()) >= 8,
            "url": base_of(request), "path": "/rest"}


@admin_routes.get("/api/music/app")
async def app_state(request: Request, _: str = Depends(require_admin)):
    return app_view(request)


@admin_routes.post("/api/music/app")
async def app_set(request: Request, user: str = Depends(require_admin)):
    payload = await body(request)
    enabled = bool(payload.get("enabled"))
    updates = {"ATENA_MUSIC_SUBSONIC": "1" if enabled else "0"}
    if enabled and (payload.get("regenerate") or len(conf.app_password()) < 8):
        updates["ATENA_MUSIC_APP_PASSWORD"] = secrets.token_urlsafe(12)
    write_env(updates)
    return app_view(request)
