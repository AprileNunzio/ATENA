import logging
import time

import httpx

from features.music import catalog, covers, naming, scanner, sources
from features.music.db import db

log = logging.getLogger("atena.music")
RETRY = 30 * 86400
BATCH = 40


def mark(track_id: int) -> None:
    db.run("INSERT INTO lookups(track_id, kind, at) VALUES(?,?,?) ON CONFLICT(track_id, kind) DO UPDATE SET at=excluded.at", (track_id, "meta", time.time()))


def candidates() -> list[dict]:
    rows = db.rows("SELECT id, title, artist, album_artist, album, genre, year, track_no FROM tracks WHERE id NOT IN "
                   "(SELECT track_id FROM lookups WHERE kind='meta' AND at>?) ORDER BY added DESC LIMIT ?", (time.time() - RETRY, BATCH * 5))
    return [r for r in rows if naming.no_album(r["album"]) and not naming.no_artist(r["artist"])][:BATCH]


def swapped(row: dict, found: dict) -> bool:
    direct = sources.match(row["title"], row["artist"], found["title"], found["artist"])
    return not direct and sources.match(row["artist"], row["title"], found["title"], found["artist"])


def apply(row: dict, found: dict) -> str:
    album = str(found.get("album") or "").strip()[:200]
    if not album:
        return ""
    artist, title = row["artist"], row["title"]
    album_artist = row["album_artist"]
    if swapped(row, found):
        artist, title, album_artist = found["artist"], found["title"], found["artist"]
    genre = row["genre"] or str(found.get("genre") or "")[:80]
    key = catalog.key(album_artist, album)
    db.run("UPDATE tracks SET title=?, artist=?, album_artist=?, album=?, album_key=?, artist_key=?, year=?, genre=?, track_no=? WHERE id=?",
           (title, artist, album_artist, album, key, catalog.key(artist), row["year"] or found.get("year") or 0, genre, row["track_no"] or found.get("track_no") or 0, row["id"]))
    scanner.index_text(row["id"], {"title": title, "artist": artist, "album": album, "genre": genre})
    return key


async def save_cover(client: httpx.AsyncClient, key: str, found: dict) -> None:
    url = str(found.get("cover") or "")
    if not url.startswith("https://") or covers.stored(key).is_file():
        return
    try:
        image = await client.get(url)
    except httpx.HTTPError:
        return
    if image.status_code == 200 and 1000 < len(image.content) < covers.MAX_IMAGE:
        covers.stored(key).write_bytes(image.content)
        db.run("UPDATE tracks SET cover=1 WHERE album_key=?", (key,))


async def run(limit: int = 8) -> int:
    done = 0
    async with sources.client() as client:
        for row in candidates()[:limit]:
            found = await sources.search(client, row["artist"], row["title"])
            mark(row["id"])
            key = apply(row, found) if found else ""
            if key:
                done += 1
                await save_cover(client, key, found)
    return done
