import hashlib
import logging
import os
import time
from pathlib import Path

from features.music import catalog, covers, layout, tags
from features.music.db import db

log = logging.getLogger("atena.music")
BATCH = 40
PAUSE = 0.02
progress = {"running": False, "total": 0, "done": 0, "added": 0, "updated": 0, "removed": 0, "started": 0.0,
            "finished": 0.0, "error": "", "last_full": 0.0}


def relative(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def walk(base: Path) -> list[Path]:
    found = []
    for folder, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        found += [Path(folder) / f for f in files if layout.is_audio(Path(f))]
    return found


def fingerprint(info: dict) -> str:
    return hashlib.sha1(f"{info['artist'].lower()}|{info['title'].lower()}|{round(info['duration'] / 3)}".encode("utf-8")).hexdigest()[:16]


def has_picture(path: Path, info: dict, folders: dict) -> bool:
    if info["cover"]:
        return True
    if path.parent not in folders:
        folders[path.parent] = covers.folder_image(path.parent) is not None
    return folders[path.parent]


def fields(info: dict, stat: os.stat_result, rel: str, now: float) -> dict:
    return {"path": rel, "mtime": stat.st_mtime, "size": stat.st_size, "title": info["title"][:300], "artist": info["artist"][:200],
            "album_artist": info["album_artist"][:200], "album": info["album"][:200], "track_no": info["track_no"], "disc_no": info["disc_no"],
            "year": info["year"], "genre": info["genre"][:80], "duration": info["duration"], "bitrate": info["bitrate"],
            "cover": int(info["cover"]), "album_key": catalog.key(info["album_artist"], info["album"]),
            "artist_key": catalog.key(info["artist"]), "added": now, "fingerprint": fingerprint(info)}


def store(row: dict, existing: dict | None) -> int:
    if existing:
        columns = [c for c in row if c not in ("added", "path")]
        sets = ", ".join(f"{c}=?" for c in columns)
        db.run(f"UPDATE tracks SET {sets} WHERE id=?", (*[row[c] for c in columns], existing["id"]))
        return existing["id"]
    names = ", ".join(row)
    return db.run(f"INSERT INTO tracks({names}) VALUES({','.join('?' * len(row))})", tuple(row.values()))


def index_text(track_id: int, row: dict) -> None:
    if not db.fts:
        return
    db.run("DELETE FROM tracks_fts WHERE rowid=?", (track_id,))
    db.run("INSERT INTO tracks_fts(rowid, title, artist, album, genre) VALUES(?,?,?,?,?)",
           (track_id, row["title"], row["artist"], row["album"], row["genre"]))


def drop(ids: list[int]) -> None:
    for chunk in range(0, len(ids), 200):
        part = tuple(ids[chunk:chunk + 200])
        marks = ",".join("?" * len(part))
        for table, column in (("tracks", "id"), ("playlist_tracks", "track_id"), ("likes", "track_id"), ("ratings", "track_id")):
            db.run(f"DELETE FROM {table} WHERE {column} IN ({marks})", part)
        if db.fts:
            db.run(f"DELETE FROM tracks_fts WHERE rowid IN ({marks})", part)


def changed(files: list[Path], known: dict, base: Path, full: bool) -> tuple[list, set]:
    seen, todo = set(), []
    for path in files:
        rel = relative(path, base)
        seen.add(rel)
        try:
            stat = path.stat()
        except OSError:
            continue
        old = known.get(rel)
        if full or not old or abs(old["mtime"] - stat.st_mtime) > 1 or old["size"] != stat.st_size:
            todo.append((path, rel, stat, old))
    return todo, seen


def scan(full: bool = False) -> dict:
    if progress["running"]:
        return dict(progress)
    base = layout.root()
    progress.update(running=True, total=0, done=0, added=0, updated=0, removed=0, started=time.time(), error="")
    try:
        known = {r["path"]: r for r in db.rows("SELECT id, path, mtime, size FROM tracks")}
        todo, seen = changed(walk(layout.library()), known, base, full)
        progress["total"] = len(todo)
        folders: dict = {}
        for index, (path, rel, stat, old) in enumerate(todo, 1):
            info = tags.read(path)
            info["cover"] = has_picture(path, info, folders) or covers.stored(catalog.key(info["album_artist"], info["album"])).is_file()
            row = fields(info, stat, rel, time.time())
            index_text(store(row, old), row)
            progress["updated" if old else "added"] += 1
            progress["done"] = index
            if index % BATCH == 0:
                time.sleep(PAUSE)
        gone = [r["id"] for rel, r in known.items() if rel not in seen]
        if gone:
            drop(gone)
        progress["removed"] = len(gone)
        if full:
            progress["last_full"] = time.time()
    except Exception as exc:
        log.warning("Scansione della libreria non riuscita: %s", exc)
        progress["error"] = str(exc)[:200]
    finally:
        progress.update(running=False, finished=time.time())
    return dict(progress)


def duplicates() -> list[dict]:
    return db.rows("SELECT fingerprint, COUNT(*) copies, MIN(title) title, MIN(artist) artist FROM tracks WHERE fingerprint<>'' "
                   "GROUP BY fingerprint HAVING copies>1 ORDER BY copies DESC LIMIT 200")


def duplicate_files(fingerprint_value: str) -> list[dict]:
    return db.rows("SELECT id, path, size, bitrate, duration FROM tracks WHERE fingerprint=? ORDER BY bitrate DESC, size DESC",
                   (fingerprint_value,))
