import logging
from pathlib import Path

import httpx

from config import STATE_DIR
from features.music import layout, naming, tags
from features.music.db import db

log = logging.getLogger("atena.music")
CACHE = STATE_DIR / "music_covers"
SIZES = (96, 300, 600)
FOLDER_NAMES = ("cover", "folder", "front", "album", "albumart", "artwork")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
USER_AGENT = "AtenaOS/3 (+https://github.com/AprileNunzio/ATENA)"
MAX_IMAGE = 6 * 1024 * 1024


def snap(size) -> int:
    try:
        wanted = int(size)
    except (TypeError, ValueError):
        return 300
    return min(SIZES, key=lambda s: abs(s - wanted))


def stored(album_key: str) -> Path:
    return layout.covers() / f"{album_key}.jpg"


def folder_image(directory: Path) -> Path | None:
    try:
        entries = {p.name.lower(): p for p in directory.iterdir() if p.is_file()}
    except OSError:
        return None
    for base in FOLDER_NAMES:
        for ext in IMAGE_EXT:
            if base + ext in entries:
                return entries[base + ext]
    return None


def find(album_key: str) -> bytes | None:
    saved = stored(album_key)
    if saved.is_file():
        return saved.read_bytes()
    rows = db.rows("SELECT path, cover FROM tracks WHERE album_key=? ORDER BY cover DESC, disc_no, track_no LIMIT 6", (album_key,))
    base = layout.root()
    for row in rows:
        path = base / row["path"]
        if row["cover"]:
            data = tags.embedded_cover(path)
            if data:
                return data
    for row in rows[:1]:
        image = folder_image((base / row["path"]).parent)
        if image is not None and image.stat().st_size < MAX_IMAGE:
            return image.read_bytes()
    return None


def resize(data: bytes, size: int) -> bytes:
    try:
        import cv2
        import numpy as np
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return data
        height, width = image.shape[:2]
        scale = size / max(height, width)
        if scale < 1:
            image = cv2.resize(image, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 86])
        return bytes(buffer) if ok else data
    except (ImportError, ValueError, OSError):
        return data


def thumbnail(album_key: str, size) -> bytes | None:
    pixels = snap(size)
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"{album_key}_{pixels}.jpg"
    if target.is_file():
        return target.read_bytes()
    data = find(album_key)
    if data is None:
        return None
    out = resize(data, pixels)
    try:
        target.write_bytes(out)
    except OSError as exc:
        log.warning("Copertina non messa in cache: %s", exc)
    return out


def forget(album_key: str) -> None:
    for size in SIZES:
        (CACHE / f"{album_key}_{size}.jpg").unlink(missing_ok=True)


def missing(limit: int = 12) -> list[dict]:
    rows = db.rows("SELECT album_key, album, album_artist, MIN(path) path FROM tracks WHERE cover=0 GROUP BY album_key LIMIT ?", (limit * 4,))
    base = layout.root()
    out = []
    for row in rows:
        if stored(row["album_key"]).is_file() or folder_image((base / row["path"]).parent) is not None:
            continue
        if naming.no_album(row["album"]):
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


async def lookup(client: httpx.AsyncClient, album: str, artist: str) -> bytes | None:
    try:
        reply = await client.get("https://itunes.apple.com/search", params={"term": f"{artist} {album}", "entity": "album", "limit": 3, "country": "it"})
        results = reply.json().get("results", [])
    except (httpx.HTTPError, ValueError):
        return None
    wanted = album.lower()
    best = next((r for r in results if wanted in r.get("collectionName", "").lower()), None)
    url = (best or {}).get("artworkUrl100", "").replace("100x100", "600x600")
    if not url.startswith("https://"):
        return None
    try:
        image = await client.get(url)
    except httpx.HTTPError:
        return None
    return image.content if image.status_code == 200 and 1000 < len(image.content) < MAX_IMAGE else None


async def complete(limit: int = 12) -> int:
    pending = missing(limit)
    if not pending:
        return 0
    saved = 0
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": USER_AGENT}) as client:
        for row in pending:
            data = await lookup(client, row["album"], row["album_artist"])
            if data is None:
                continue
            try:
                stored(row["album_key"]).write_bytes(data)
            except OSError as exc:
                log.warning("Copertina non salvata: %s", exc)
                continue
            forget(row["album_key"])
            db.run("UPDATE tracks SET cover=1 WHERE album_key=?", (row["album_key"],))
            saved += 1
    return saved
