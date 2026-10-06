import asyncio
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from access import require_admin
from features.music import catalog, conf, covers, enrich, hints, identify, layout, listening, lyrics, lyrics_store, mixes, organizer, renamer, scanner, stream, tagwriter, tags
from features.music.db import db
from features.music.service import library
from state import store

admin_routes = APIRouter()
MAX_UPLOAD = 400 * 1024 * 1024
EDITABLE = ("title", "artist", "album", "album_artist", "genre")


async def body(request: Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(400, "Richiesta non valida")
    if not isinstance(data, dict):
        raise HTTPException(400, "Richiesta non valida")
    return data


def need_track(track_id: int) -> dict:
    found = catalog.track(track_id)
    if not found:
        raise HTTPException(404, "Brano non trovato")
    return found


@admin_routes.get("/api/music/library")
async def overview(_: str = Depends(require_admin)):
    return {**catalog.stats(), "service": library.view(), "tags": tags.TinyTag is not None, "ffmpeg": bool(stream.ffmpeg()),
            "root": str(layout.root()), "prefs": {"crossfade": conf.crossfade(), "radio": conf.radio(), "lyrics": conf.lyrics_online(),
                                                  "cast": conf.cast_enabled(), "share": conf.share_links(), "subsonic": conf.subsonic_enabled()}}


@admin_routes.get("/api/music/home")
async def home(user: str = Depends(require_admin)):
    return await asyncio.to_thread(mixes.home, user)


@admin_routes.get("/api/music/tracks")
async def tracks(sort: str = "recent", limit: int = 60, offset: int = 0, genre: str = "", liked: bool = False, user: str = Depends(require_admin)):
    where, params = [], []
    if genre:
        where.append("genre=?")
        params.append(genre)
    if liked:
        where.append("id IN (SELECT track_id FROM likes WHERE user=?)")
        params.append(user)
    rows = catalog.tracks(sort, limit, offset, user, " AND ".join(where), tuple(params))
    return {"tracks": rows, "total": db.scalar("SELECT COUNT(*) FROM tracks")}


@admin_routes.get("/api/music/tracks/lookup")
async def lookup(ids: str = "", user: str = Depends(require_admin)):
    wanted = [i for i in ids.split(",")[:500] if i.strip().isdigit()]
    return {"tracks": catalog.by_ids([int(i) for i in wanted], user)}


@admin_routes.get("/api/music/search")
async def search(q: str = "", user: str = Depends(require_admin)):
    return catalog.search(q, 40, user)


@admin_routes.get("/api/music/albums")
async def albums(sort: str = "title", limit: int = 60, offset: int = 0, genre: str = "", year: int = 0, _: str = Depends(require_admin)):
    return {"albums": catalog.albums(sort, limit, offset, genre, year)}


@admin_routes.get("/api/music/albums/{album_key}")
async def album(album_key: str, user: str = Depends(require_admin)):
    found = catalog.album(album_key, user)
    if not found:
        raise HTTPException(404, "Album non trovato")
    return found


@admin_routes.get("/api/music/artists")
async def artists(limit: int = 300, offset: int = 0, _: str = Depends(require_admin)):
    return {"artists": catalog.artists(limit, offset)}


@admin_routes.get("/api/music/artists/{artist_key}")
async def artist(artist_key: str, user: str = Depends(require_admin)):
    found = catalog.artist(artist_key, user)
    if not found:
        raise HTTPException(404, "Artista non trovato")
    return found


@admin_routes.get("/api/music/genres")
async def genres(_: str = Depends(require_admin)):
    return {"genres": catalog.genres(), "decades": catalog.decades()}


@admin_routes.get("/api/music/mix/{identifier:path}")
async def mix(identifier: str, user: str = Depends(require_admin)):
    return {"tracks": await asyncio.to_thread(mixes.mix, identifier, user)}


@admin_routes.post("/api/music/radio")
async def radio(request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    if not conf.radio():
        return {"tracks": []}
    try:
        seed = int(data.get("seed"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Brano di partenza non valido")
    return {"tracks": await asyncio.to_thread(mixes.similar, seed, user, list(data.get("exclude") or [])[:300], 15)}


@admin_routes.get("/api/music/stream/{track_id}")
async def play(track_id: int, request: Request, fmt: str = "", _: str = Depends(require_admin)):
    found = db.row("SELECT path FROM tracks WHERE id=?", (track_id,))
    if not found:
        raise HTTPException(404, "Brano non trovato")
    return stream.serve(layout.root() / found["path"], request, fmt)


@admin_routes.get("/api/music/cover/{album_key}")
async def cover(album_key: str, size: int = 300, _: str = Depends(require_admin)):
    data = await asyncio.to_thread(covers.thumbnail, album_key[:24], size)
    if data is None:
        raise HTTPException(404, "Nessuna copertina")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@admin_routes.get("/api/music/lyrics/{track_id}")
async def words(track_id: int, _: str = Depends(require_admin)):
    found = need_track(track_id)
    sidecar = (layout.root() / found["path"]).with_suffix(".lrc")
    try:
        text = sidecar.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    if text:
        synced = lyrics._parse(text)
        return {"synced": synced} if synced else {"plain": text[:4000]}
    if not conf.lyrics_online():
        return {}
    return await lyrics.fetch(found["title"], found["artist"], found["album"], found["duration"] or None)


@admin_routes.post("/api/music/tracks/{track_id}/like")
async def like(track_id: int, request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    if not listening.like(user, track_id, bool(data.get("on", True))):
        raise HTTPException(404, "Brano non trovato")
    return {"liked": bool(data.get("on", True))}


@admin_routes.post("/api/music/tracks/{track_id}/rate")
async def rate(track_id: int, request: Request, user: str = Depends(require_admin)):
    stars = (await body(request)).get("stars", 0)
    if not listening.rate(user, track_id, int(stars or 0)):
        raise HTTPException(404, "Brano non trovato")
    return {"stars": max(0, min(5, int(stars or 0)))}


@admin_routes.post("/api/music/tracks/{track_id}/played")
async def played(track_id: int, request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    counted = listening.played(user, track_id, float(data.get("seconds") or 0), bool(data.get("done")), str(data.get("source") or "web"))
    return {"counted": counted}


@admin_routes.get("/api/music/history")
async def history(limit: int = 50, user: str = Depends(require_admin)):
    return {"tracks": listening.recent(user, limit)}


@admin_routes.get("/api/music/stats")
async def stats(days: int = 30, user: str = Depends(require_admin)):
    return await asyncio.to_thread(listening.summary, user, max(1, min(365, days)))


def apply_edit(track_id: int, data: dict, scope: str) -> int:
    found = need_track(track_id)
    changes = {k: str(data[k]).strip()[:200] for k in EDITABLE if k in data and str(data[k]).strip()}
    for key in ("year", "track_no"):
        if key in data:
            try:
                changes[key] = max(0, min(9999, int(data[key])))
            except (TypeError, ValueError):
                raise HTTPException(400, "Numero non valido")
    if scope == "album":
        for key in ("title", "track_no", "artist"):
            changes.pop(key, None)
    if not changes:
        raise HTTPException(400, "Nessuna modifica")
    changes["album_key"] = catalog.key(changes.get("album_artist", found["album_artist"]), changes.get("album", found["album"]))
    if scope != "album":
        changes["artist_key"] = catalog.key(changes.get("artist", found["artist"]))
    where, ref = ("album_key=?", found["album_key"]) if scope == "album" else ("id=?", track_id)
    ids = [r["id"] for r in db.rows(f"SELECT id FROM tracks WHERE {where}", (ref,))]
    sets = ", ".join(f"{k}=?" for k in changes)
    db.run(f"UPDATE tracks SET {sets} WHERE {where}", (*changes.values(), ref))
    for row in db.rows(f"SELECT id, title, artist, album, genre FROM tracks WHERE id IN ({','.join('?' * len(ids))})", tuple(ids)):
        scanner.index_text(row["id"], row)
    return len(ids)


@admin_routes.post("/api/music/tracks/{track_id}/edit")
async def edit(track_id: int, request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    changed = await asyncio.to_thread(apply_edit, track_id, data, "album" if data.get("scope") == "album" else "track")
    store.event("INFO", f"Metadati musicali modificati da {user} ({changed} brani)", "music")
    return {"changed": changed}


@admin_routes.post("/api/music/tracks/{track_id}/trash")
async def trash(track_id: int, user: str = Depends(require_admin)):
    found = db.row("SELECT path FROM tracks WHERE id=?", (track_id,))
    if not found:
        raise HTTPException(404, "Brano non trovato")
    source = layout.root() / found["path"]
    relative = Path(found["path"]).relative_to(layout.LIBRARY)
    target = organizer.unique(layout.trash() / relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if layout.inside(layout.library(), source) and source.exists():
        shutil.move(str(source), str(target))
    scanner.drop([track_id])
    store.event("INFO", f"Brano spostato nel cestino da {user}: {found['path']} → {target.relative_to(layout.root()).as_posix()}", "music")
    return {"ok": True, "to": target.relative_to(layout.root()).as_posix()}


def trashed() -> list[dict]:
    found = []
    for base in (layout.trash(), layout.library() / layout.OLD_TRASH):
        if base.is_dir():
            found += [p for p in base.rglob("*") if p.is_file() and layout.is_audio(p)]
    return [{"path": p.relative_to(layout.root()).as_posix(), "name": p.name} for p in sorted(found)[:300]]


@admin_routes.get("/api/music/trash")
async def trash_list(_: str = Depends(require_admin)):
    return {"files": await asyncio.to_thread(trashed), "moves": organizer.progress["moves"]}


@admin_routes.post("/api/music/trash/restore")
async def trash_restore(request: Request, user: str = Depends(require_admin)):
    path = str((await body(request)).get("path") or "")
    source = layout.root() / path
    if not (layout.inside(layout.trash(), source) or layout.inside(layout.library() / layout.OLD_TRASH, source)) or not source.is_file():
        raise HTTPException(404, "File non trovato nel cestino")
    shutil.move(str(source), str(organizer.unique(layout.inbox() / source.name)))
    store.event("INFO", f"Brano ripristinato dal cestino da {user}: {path}", "music")
    result = await library.run_now(False)
    return {"ok": True, "result": result}


@admin_routes.post("/api/music/scan")
async def rescan(request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    store.event("INFO", f"Scansione della libreria richiesta da {user}", "music")
    result = await library.run_now(bool(data.get("full")))
    return {**library.view(), "result": result}


@admin_routes.get("/api/music/duplicates")
async def duplicates(_: str = Depends(require_admin)):
    found = await asyncio.to_thread(scanner.duplicates)
    for row in found[:50]:
        row["files"] = scanner.duplicate_files(row["fingerprint"])
    return {"duplicates": found}


@admin_routes.put("/api/music/upload")
async def upload(request: Request, name: str = "", user: str = Depends(require_admin)):
    if request.headers.get("X-Atena-Request") != "1":
        raise HTTPException(403, "Richiesta non valida")
    clean = organizer.name(Path(name).name, "brano")
    if not layout.is_audio(Path(clean)):
        raise HTTPException(415, "Formato audio non supportato")
    declared = int(request.headers.get("content-length") or 0)
    if declared > MAX_UPLOAD:
        raise HTTPException(413, "File troppo grande")
    target = organizer.unique(layout.inbox() / clean)
    written = 0
    try:
        with open(target, "wb") as handle:
            async for chunk in request.stream():
                written += len(chunk)
                if written > MAX_UPLOAD:
                    raise HTTPException(413, "File troppo grande")
                handle.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(500, f"Salvataggio non riuscito: {exc}")
    target.touch()
    library.trigger()
    store.event("INFO", f"Brano caricato da {user}: {clean}", "music")
    return {"saved": target.name, "bytes": written, "at": time.time()}


@admin_routes.post("/api/music/identify")
async def identify_now(user: str = Depends(require_admin)):
    result = await identify.run(10, conf.write_tags())
    renamed = await asyncio.to_thread(renamer.run, 200)
    store.event("INFO", f"Riconoscimento dei brani richiesto da {user}: {result['identified']} su {result['tried']}", "music")
    return {**result, **renamed}


@admin_routes.get("/api/music/unassigned")
async def unassigned(_: str = Depends(require_admin)):
    return {"files": await asyncio.to_thread(organizer.unassigned_files)}


@admin_routes.post("/api/music/assign")
async def assign(request: Request, user: str = Depends(require_admin)):
    data = await body(request)
    source = layout.root() / str(data.get("path") or "")
    if not (layout.inside(layout.inbox(), source) or source.parent == layout.root()) or not source.is_file() or not layout.is_audio(source):
        raise HTTPException(404, "File non trovato in «Da smistare»")
    if data.get("mix"):
        fields = {"artist": "Vari artisti", "album": "Mix"}
    else:
        fields = {k: str(data.get(k) or "").strip()[:200] for k in ("artist", "album", "genre")}
        if not fields["artist"]:
            raise HTTPException(400, "Serve almeno l'artista (oppure scegli «Metti nei Mix»)")
    for key in ("year", "track_no"):
        try:
            fields[key] = max(0, min(9999, int(data.get(key) or 0)))
        except (TypeError, ValueError):
            raise HTTPException(400, "Numero non valido")
    fields["title"] = str(data.get("title") or "").strip()[:300]
    hints.put(source, fields, force=True)
    if conf.write_tags():
        await asyncio.to_thread(tagwriter.write, source, fields)
    organizer.held.pop(source, None)
    store.event("INFO", f"Brano assegnato da {user}: {source.name} → {fields.get('artist')} / {fields.get('album') or 'Singoli'}", "music")
    return {"ok": True, "result": await library.run_now(False)}


@admin_routes.get("/api/music/rename/preview")
async def rename_preview(_: str = Depends(require_admin)):
    steps = await asyncio.to_thread(renamer.plan, 400)
    return {"total": len(steps), "steps": steps[:40]}


@admin_routes.post("/api/music/rename")
async def rename_all(user: str = Depends(require_admin)):
    result = await asyncio.to_thread(renamer.run, 1000)
    store.event("INFO", f"Nomi completi applicati da {user}: {result['renamed']} file", "music")
    return result


@admin_routes.get("/api/music/covers/missing")
async def covers_missing(_: str = Depends(require_admin)):
    return {"albums": await asyncio.to_thread(covers.missing, 50)}


@admin_routes.post("/api/music/covers/complete")
async def covers_complete(_: str = Depends(require_admin)):
    saved = await covers.complete(12)
    enriched = await enrich.run(12)
    texts = await lyrics_store.fetch_missing(15)
    return {"saved": saved + enriched, "enriched": enriched, "lyrics": texts}
