from pathlib import Path

from access import require_admin
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.background import BackgroundTask
from state import store

from features.tv import relay, targets
from features.tv.m3u import MAX_BYTES, PlaylistError
from features.tv.store import tv_store

admin_routes = APIRouter()
public_routes = APIRouter()
WATCH = Path(__file__).resolve().parent / "watch.html"


def _bad(exc: Exception, code: int = 400):
    raise HTTPException(code, str(exc))


@admin_routes.get("/api/tv")
async def tv_overview(_: str = Depends(require_admin)):
    channels = tv_store.channels()
    groups = sorted({c["group"] for c in channels if c["group"]})
    return {"playlists": tv_store.playlists(), "count": len(channels), "groups": groups, "favorites": tv_store.favorites()}


@admin_routes.get("/api/tv/channels")
async def tv_channels(q: str = "", group: str = "", fav: bool = False, page: int = 1, _: str = Depends(require_admin)):
    favorites = set(tv_store.favorites())
    needle = q.strip().lower()[:80]
    rows = [c for c in tv_store.channels() if (not group or c["group"] == group) and (not fav or c["id"] in favorites)
            and (not needle or needle in c["name"].lower())]
    rows.sort(key=lambda c: (c["id"] not in favorites, c["name"].lower()))
    page = max(1, page)
    view = [{k: c[k] for k in ("id", "name", "group", "logo")} | {"favorite": c["id"] in favorites}
            for c in rows[(page - 1) * 60: page * 60]]
    return {"channels": view, "total": len(rows), "page": page}


@admin_routes.post("/api/tv/playlists")
async def tv_add(request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    text = str(body.get("text") or "")
    if len(text) > MAX_BYTES:
        _bad(PlaylistError("Playlist troppo grande"))
    try:
        entry = tv_store.add(str(body.get("name") or ""), str(body.get("url") or ""), text)
        if entry["source"] == "url":
            entry = await tv_store.refresh(entry["id"])
    except PlaylistError as exc:
        _bad(exc)
    store.event("INFO", f"Playlist TV «{entry['name']}» aggiunta da {user}: {entry['count']} canali", "tv")
    return entry


@admin_routes.post("/api/tv/playlists/{pid}/refresh")
async def tv_refresh(pid: str, _: str = Depends(require_admin)):
    try:
        return await tv_store.refresh(pid)
    except PlaylistError as exc:
        _bad(exc, 502)


@admin_routes.delete("/api/tv/playlists/{pid}")
async def tv_remove(pid: str, user: str = Depends(require_admin)):
    try:
        tv_store.remove(pid)
    except PlaylistError as exc:
        _bad(exc)
    store.event("INFO", f"Playlist TV {pid} rimossa da {user}", "tv")
    return {"ok": True}


@admin_routes.put("/api/tv/favorites/{cid}")
async def tv_favorite(cid: str, request: Request, _: str = Depends(require_admin)):
    try:
        return {"favorites": tv_store.set_favorite(cid, bool((await request.json()).get("on")))}
    except PlaylistError as exc:
        _bad(exc)


@admin_routes.get("/api/tv/targets")
async def tv_targets(discover: bool = False, _: str = Depends(require_admin)):
    return {"targets": await targets.listing(discover)}


@admin_routes.post("/api/tv/play")
async def tv_play(request: Request, user: str = Depends(require_admin)):
    body = await request.json()
    channel = tv_store.channel(str(body.get("channel") or ""))
    if not channel:
        raise HTTPException(404, "Canale sconosciuto")
    try:
        where = await targets.play(channel, str(body.get("target") or "display"), user)
    except targets.TargetError as exc:
        _bad(exc, 409)
    return {"ok": True, "where": where, "preview": targets.live_path(channel)}


@admin_routes.get("/api/tv/preview/{cid}")
async def tv_preview(cid: str, _: str = Depends(require_admin)):
    channel = tv_store.channel(cid)
    if not channel:
        raise HTTPException(404, "Canale sconosciuto")
    return {"src": targets.live_path(channel), "name": channel["name"]}


@admin_routes.post("/api/tv/stop")
async def tv_stop(_: str = Depends(require_admin)):
    targets.stop_display()
    return {"ok": True}


@admin_routes.get("/tv/watch")
@public_routes.get("/tv/watch")
async def tv_watch():
    return FileResponse(WATCH, media_type="text/html", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


async def _relay(cid: str, url: str, token: str, wanted_range: str | None = None) -> Response:
    channel = tv_store.channel(cid)
    if not channel or not relay.valid(cid, token):
        raise HTTPException(401, "Collegamento scaduto o non valido")
    if not relay.allowed(channel["url"], url):
        raise HTTPException(403, "Sorgente non ammessa")
    try:
        client, res = await relay.open_upstream(url, relay.range_header(wanted_range))
    except relay.RelayError as exc:
        raise HTTPException(502, str(exc))
    kind = res.headers.get("content-type", "application/octet-stream")
    if relay.is_playlist(str(res.url), kind):
        try:
            text = await relay.read_playlist(res)
        except relay.RelayError as exc:
            raise HTTPException(502, str(exc))
        finally:
            await res.aclose()
            await client.aclose()
        body = relay.rewrite(text, str(res.url), cid, token, channel["url"])
        return Response(body, media_type="application/vnd.apple.mpegurl", headers=relay.CORS)

    async def close() -> None:
        await res.aclose()
        await client.aclose()
    passed = {k: v for k, v in res.headers.items() if k.lower() in relay.PASS_HEADERS}
    return StreamingResponse(res.aiter_raw(), status_code=206 if res.status_code == 206 else 200,
                             media_type=kind.split(";")[0][:80], headers={**relay.CORS, **passed},
                             background=BackgroundTask(close))


@admin_routes.get("/api/tv/live/{cid}")
@public_routes.get("/api/tv/live/{cid}")
async def tv_live(cid: str, request: Request, t: str = ""):
    channel = tv_store.channel(cid)
    if not channel:
        raise HTTPException(404, "Canale sconosciuto")
    return await _relay(cid, channel["url"], t, request.headers.get("range"))


@admin_routes.get("/api/tv/seg/{cid}")
@public_routes.get("/api/tv/seg/{cid}")
async def tv_segment(cid: str, request: Request, u: str = "", s: str = "", t: str = ""):
    try:
        url = relay.decode(cid, u[:4000], s)
    except relay.RelayError as exc:
        raise HTTPException(403, str(exc))
    return await _relay(cid, url, t, request.headers.get("range"))
