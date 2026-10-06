import json
import time
from pathlib import Path

from features.music import naming
from features.music.db import db

FIELDS = ("title", "artist", "album", "genre", "year", "track_no")


def put(path: Path, data: dict, force: bool = False) -> None:
    clean = {k: data[k] for k in FIELDS if data.get(k) not in (None, "", 0)}
    if force:
        clean["_force"] = True
    db.run("INSERT INTO hints(path, data, at) VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET data=excluded.data, at=excluded.at",
           (str(path), json.dumps(clean, ensure_ascii=False), time.time()))


def get(path: Path) -> dict:
    row = db.row("SELECT data FROM hints WHERE path=?", (str(path),))
    try:
        return json.loads(row["data"]) if row else {}
    except ValueError:
        return {}


def drop(path: Path) -> None:
    db.run("DELETE FROM hints WHERE path=?", (str(path),))


def overlay(path: Path, info: dict, force: bool = False) -> dict:
    hint = get(path)
    if not hint:
        return info
    out = dict(info)
    force = force or bool(hint.pop("_force", False))
    for key, value in hint.items():
        current = out.get(key)
        missing = (naming.no_artist(current) if key == "artist" else naming.no_album(current) if key == "album" else not current)
        if force or missing:
            out[key] = value
    if hint.get("artist") and (force or naming.no_artist(out.get("album_artist"))):
        out["album_artist"] = hint["artist"]
    return out
