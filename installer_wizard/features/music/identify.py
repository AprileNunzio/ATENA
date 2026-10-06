import asyncio
import logging
import shutil
import time
from pathlib import Path

import httpx

from features.music import catalog, covers, hints, layout, music, naming, scanner, sources, tagwriter, tags
from features.music.db import db

log = logging.getLogger("atena.music")
RETRY = 30 * 86400
POOL = 200
SAMPLE_SECONDS = 12
COLUMNS = "id, path, title, artist, album_artist, album, genre, year, track_no, disc_no, duration"


def untitled(row: dict) -> bool:
    title = naming.squash(row["title"])
    return not title or title == naming.squash(Path(row["path"]).stem)


def lacking(row: dict) -> bool:
    return naming.no_artist(row["artist"]) or naming.no_album(row["album"]) or untitled(row)


def candidates(limit: int) -> list[dict]:
    rows = db.rows(f"SELECT {COLUMNS} FROM tracks WHERE id NOT IN (SELECT track_id FROM lookups WHERE kind='identify' AND at>?) ORDER BY added DESC LIMIT ?",
                   (time.time() - RETRY, POOL))
    return [r for r in rows if lacking(r)][:limit]


def mark(track_id: int) -> None:
    db.run("INSERT INTO lookups(track_id, kind, at) VALUES(?,?,?) ON CONFLICT(track_id, kind) DO UPDATE SET at=excluded.at", (track_id, "identify", time.time()))


def sample_command(path: Path, duration: float) -> list[str]:
    start = max(0.0, min(duration * 0.3, duration - SAMPLE_SECONDS - 1)) if duration > SAMPLE_SECONDS + 5 else 0.0
    return [shutil.which("ffmpeg") or "ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{start:.1f}", "-t", str(SAMPLE_SECONDS), "-i", str(path),
            "-vn", "-ac", "1", "-ar", "44100", "-f", "wav", "pipe:1"]


async def excerpt(path: Path, duration: float) -> bytes:
    if not shutil.which("ffmpeg"):
        return b""
    proc = await asyncio.create_subprocess_exec(*sample_command(path, duration), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        data, _ = await asyncio.wait_for(proc.communicate(), 30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return b""
    return data


async def fingerprint(row: dict) -> dict | None:
    wav = await excerpt(layout.root() / row["path"], row["duration"] or 0)
    if len(wav) < 20000:
        return None
    raw = await music.watcher._recognize(wav)
    return music.MusicWatcher._parse(raw)


def same_artist(row: dict, found: dict) -> bool:
    wanted, got = naming.squash(row["artist"]), naming.squash(found.get("artist"))
    return naming.no_artist(row["artist"]) or wanted in got or got in wanted


def usable(row: dict, found: dict | None) -> bool:
    return bool(found and found.get("title") and found.get("artist") and same_artist(row, found))


async def details(found: dict) -> dict:
    async with sources.client() as client:
        try:
            extra = await sources.search(client, found["artist"], found["title"])
        except Exception as exc:
            log.info("Dati aggiuntivi non disponibili: %s", exc)
            extra = None
    return extra or {}


def merged(found: dict, extra: dict) -> dict:
    year = str(found.get("year") or extra.get("year") or "")[:4]
    return {"title": found["title"], "artist": found["artist"], "album": found.get("album") or extra.get("album") or "",
            "genre": found.get("genre") or extra.get("genre") or "", "year": int(year) if year.isdigit() else 0,
            "track_no": int(extra.get("track_no") or 0), "cover": found.get("cover") or extra.get("cover") or ""}


def fill(row: dict, data: dict) -> dict:
    out = {}
    if untitled(row):
        out["title"] = data["title"]
    if naming.no_artist(row["artist"]):
        out["artist"] = data["artist"]
        out["album_artist"] = data["artist"]
    if naming.no_album(row["album"]) and data["album"]:
        out["album"] = data["album"]
    if not row["year"] and data["year"]:
        out["year"] = data["year"]
    if not row["genre"] and data["genre"]:
        out["genre"] = data["genre"][:80]
    if not row["track_no"] and data["track_no"]:
        out["track_no"] = data["track_no"]
    return out


def apply(row: dict, changes: dict) -> str:
    merged_row = {**row, **changes}
    key = catalog.key(merged_row["album_artist"], merged_row["album"])
    artist_key = catalog.key(merged_row["artist"])
    sets = {**changes, "album_key": key, "artist_key": artist_key}
    db.run(f"UPDATE tracks SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), row["id"]))
    scanner.index_text(row["id"], {"title": merged_row["title"], "artist": merged_row["artist"], "album": merged_row["album"], "genre": merged_row["genre"]})
    return key


async def store_cover(key: str, url: str) -> None:
    if not url.startswith("https://") or covers.stored(key).is_file():
        return
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": covers.USER_AGENT}) as client:
            image = await client.get(url)
    except httpx.HTTPError:
        return
    if image.status_code == 200 and 1000 < len(image.content) < covers.MAX_IMAGE:
        covers.stored(key).write_bytes(image.content)
        db.run("UPDATE tracks SET cover=1 WHERE album_key=?", (key,))


def write_into_file(row: dict, changes: dict) -> bool:
    path = layout.root() / row["path"]
    if not tagwriter.write(path, changes):
        return False
    stat = path.stat()
    db.run("UPDATE tracks SET mtime=?, size=? WHERE id=?", (stat.st_mtime, stat.st_size, row["id"]))
    return True


async def one(row: dict, write_tags: bool) -> dict | None:
    found = await fingerprint(row)
    if not usable(row, found):
        return None
    data = merged(found, await details(found))
    changes = fill(row, data)
    if not changes:
        return {"row": row, "changes": {}}
    key = apply(row, changes)
    await store_cover(key, data["cover"])
    if write_tags:
        await asyncio.to_thread(write_into_file, row, changes)
    return {"row": row, "changes": changes}


tried_files: dict = {}


async def inbox(paths: list[Path], write_tags: bool = True, limit: int = 3) -> int:
    done = 0
    for path in [p for p in paths if time.time() - tried_files.get(p, 0.0) > 86400][:limit]:
        info = tags.read(path)
        row = {"path": path.relative_to(layout.root()).as_posix(), "duration": info["duration"]}
        tried_files[path] = time.time()
        try:
            found = await fingerprint(row)
        except Exception as exc:
            log.warning("Riconoscimento dei brani non riuscito: %s", exc)
            break
        if not usable({"artist": naming.UNKNOWN_ARTIST}, found):
            continue
        data = merged(found, await details(found))
        hint = {k: data[k] for k in ("title", "artist", "album", "genre", "year", "track_no")}
        hints.put(path, hint)
        if write_tags:
            await asyncio.to_thread(tagwriter.write, path, hint)
        done += 1
    return done


async def run(limit: int = 3, write_tags: bool = True) -> dict:
    if not music.available():
        return {"identified": 0, "tried": 0, "available": False, "items": []}
    done, tried, items = 0, 0, []
    for row in await asyncio.to_thread(candidates, limit):
        tried += 1
        try:
            result = await one(row, write_tags)
        except Exception as exc:
            log.warning("Riconoscimento dei brani non riuscito: %s", exc)
            break
        mark(row["id"])
        if result and result["changes"]:
            done += 1
            items.append({"file": Path(row["path"]).name, **{k: v for k, v in result["changes"].items() if k in ("title", "artist", "album", "year")}})
    return {"identified": done, "tried": tried, "available": True, "items": items}
