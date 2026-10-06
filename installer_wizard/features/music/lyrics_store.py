import logging
import time
from pathlib import Path

from features.music import layout, lyrics, naming
from features.music.db import db

log = logging.getLogger("atena.music")
RETRY = 7 * 86400
BATCH = 60


def sidecar(relative: str) -> Path:
    return (layout.root() / relative).with_suffix(".lrc")


def to_lrc(data: dict) -> str:
    if data.get("synced"):
        return "\n".join(f"[{int(l['t'] // 60):02d}:{l['t'] % 60:05.2f}]{l['text']}" for l in data["synced"]) + "\n"
    return str(data.get("plain") or "").strip() + "\n"


def mark(track_id: int, kind: str = "lyrics") -> None:
    db.run("INSERT INTO lookups(track_id, kind, at) VALUES(?,?,?) ON CONFLICT(track_id, kind) DO UPDATE SET at=excluded.at", (track_id, kind, time.time()))


def candidates() -> list[dict]:
    return db.rows("SELECT id, path, title, artist, album, duration FROM tracks WHERE id NOT IN (SELECT track_id FROM lookups WHERE kind='lyrics' AND at>?) "
                   "ORDER BY added DESC LIMIT ?", (time.time() - RETRY, BATCH))


async def fetch_missing(limit: int = 10) -> int:
    saved = 0
    asked = 0
    for row in candidates():
        target = sidecar(row["path"])
        if target.exists():
            mark(row["id"])
            continue
        if asked >= limit:
            break
        asked += 1
        album = "" if naming.no_album(row["album"]) else row["album"]
        data = await lyrics.fetch(row["title"], row["artist"], album, row["duration"] or None)
        mark(row["id"])
        if not data:
            continue
        try:
            target.write_text(to_lrc(data), encoding="utf-8")
            saved += 1
        except OSError as exc:
            log.warning("Testo non salvato per %s: %s", row["title"], exc)
    return saved
