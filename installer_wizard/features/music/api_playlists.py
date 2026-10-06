import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from access import require_admin
from features.music import catalog, playlists
from features.music.api_library import body

admin_routes = APIRouter()


def ids_of(data: dict, key: str = "tracks") -> list[int]:
    raw = data.get(key)
    if not isinstance(raw, list):
        raise HTTPException(400, "Elenco non valido")
    out = []
    for item in raw[:2000]:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            raise HTTPException(400, "Elenco non valido")
    return out


@admin_routes.get("/api/music/playlists")
async def listing(user: str = Depends(require_admin)):
    return {"playlists": await asyncio.to_thread(playlists.listing, user)}


@admin_routes.post("/api/music/playlists")
async def create(request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    try:
        playlist_id = playlists.create(user, str(data.get("name") or ""), "smart" if data.get("kind") == "smart" else "manual",
                                       data.get("rule") if isinstance(data.get("rule"), dict) else None, str(data.get("description") or ""))
        if data.get("tracks"):
            playlists.add(playlist_id, user, ids_of(data))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"id": playlist_id}


@admin_routes.get("/api/music/playlists/{playlist_id}")
async def detail(playlist_id: int, user: str = Depends(require_admin)):
    found = await asyncio.to_thread(playlists.get, playlist_id, user)
    if not found:
        raise HTTPException(404, "Playlist non trovata")
    return found


@admin_routes.post("/api/music/playlists/{playlist_id}")
async def update(playlist_id: int, request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    current = playlists.owned(playlist_id, user)
    if not current:
        raise HTTPException(404, "Playlist non trovata")
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Serve un nome")
    playlists.rename(playlist_id, user, name, data.get("description") if "description" in data else None,
                     bool(data["shared"]) if "shared" in data else None, data.get("rule") if isinstance(data.get("rule"), dict) else None)
    return {"ok": True}


@admin_routes.post("/api/music/playlists/{playlist_id}/delete")
async def remove_playlist(playlist_id: int, user: str = Depends(require_admin)):
    if not playlists.delete(playlist_id, user):
        raise HTTPException(404, "Playlist non trovata")
    return {"ok": True}


@admin_routes.post("/api/music/playlists/{playlist_id}/add")
async def add(playlist_id: int, request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    try:
        return {"added": playlists.add(playlist_id, user, ids_of(data))}
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@admin_routes.post("/api/music/playlists/{playlist_id}/remove")
async def take_out(playlist_id: int, request: Request, user: str = Depends(require_admin)):
    positions = ids_of(await body(request), "positions")
    if not playlists.remove(playlist_id, user, positions):
        raise HTTPException(409, "Playlist non modificabile")
    return {"ok": True}


@admin_routes.post("/api/music/playlists/{playlist_id}/move")
async def move(playlist_id: int, request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    try:
        source, target = int(data.get("from")), int(data.get("to"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Posizione non valida")
    if not playlists.reorder(playlist_id, user, source, target):
        raise HTTPException(409, "Spostamento non possibile")
    return {"ok": True}


@admin_routes.post("/api/music/playlists/{playlist_id}/export")
async def export(playlist_id: int, user: str = Depends(require_admin)):
    target = await asyncio.to_thread(playlists.export, playlist_id, user)
    if not target:
        raise HTTPException(404, "Playlist non esportabile")
    return {"file": target.name}


@admin_routes.get("/api/music/playlists/{playlist_id}/m3u")
async def download(playlist_id: int, user: str = Depends(require_admin)):
    found = await asyncio.to_thread(playlists.get, playlist_id, user)
    if not found:
        raise HTTPException(404, "Playlist non trovata")
    return Response(playlists.m3u(found), media_type="audio/x-mpegurl",
                    headers={"Content-Disposition": f'attachment; filename="{catalog.key(found["name"])}.m3u8"'})
