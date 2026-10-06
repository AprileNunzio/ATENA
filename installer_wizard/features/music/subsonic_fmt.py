import json
import time
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from features.music import layout
from features.music.db import db

API_VERSION = "1.16.1"
ERRORS = {10: "Parametro mancante", 40: "Utente o password errati", 50: "Operazione non consentita", 70: "Elemento non trovato", 0: "Errore"}


def iso(stamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(stamp)) + ".000Z"


def song_extras(ids: list[int]) -> dict:
    if not ids:
        return {}
    rows = db.rows(f"SELECT id, size, path FROM tracks WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))
    return {r["id"]: r for r in rows}


def song(track: dict, extra: dict | None, likes: dict) -> dict:
    path = (extra or {}).get("path", "")
    suffix = Path(path).suffix.lstrip(".").lower()
    out = {"id": str(track["id"]), "parent": f"al-{track['album_key']}", "isDir": False, "title": track["title"], "album": track["album"],
           "artist": track["artist"], "track": track["track_no"] or 0, "discNumber": track["disc_no"] or 1, "year": track["year"] or 0,
           "genre": track["genre"], "size": (extra or {}).get("size", 0), "contentType": layout.mime(path), "suffix": suffix,
           "duration": int(track["duration"] or 0), "bitRate": track["bitrate"] or 0, "albumId": f"al-{track['album_key']}",
           "artistId": f"ar-{track['artist_key']}", "type": "music", "isVideo": False, "playCount": track["plays"],
           "created": iso(track["added"])}
    if track["cover"]:
        out["coverArt"] = f"al-{track['album_key']}"
    if track["id"] in likes:
        out["starred"] = iso(likes[track["id"]])
    return out


def songs(tracks: list[dict], user: str) -> list[dict]:
    ids = [t["id"] for t in tracks]
    extras = song_extras(ids)
    likes = {}
    if ids and user:
        rows = db.rows(f"SELECT track_id, at FROM likes WHERE user=? AND track_id IN ({','.join('?' * len(ids))})", (user, *ids))
        likes = {r["track_id"]: r["at"] for r in rows}
    return [song(t, extras.get(t["id"]), likes) for t in tracks]


def album(row: dict) -> dict:
    out = {"id": f"al-{row['album_key']}", "name": row["album"], "title": row["album"], "album": row["album"], "artist": row["album_artist"],
           "artistId": f"ar-{row['album_key']}", "songCount": row["tracks"], "duration": int(row.get("duration") or 0), "isDir": True,
           "year": row.get("year") or 0, "created": iso(row.get("added") or 0)}
    if row.get("cover"):
        out["coverArt"] = f"al-{row['album_key']}"
    return out


def artist(row: dict) -> dict:
    out = {"id": f"ar-{row['artist_key']}", "name": row["artist"], "albumCount": row.get("albums", 0)}
    if row.get("cover"):
        out["coverArt"] = f"ar-{row['artist_key']}"
    return out


def xml_node(name: str, value) -> str:
    if isinstance(value, list):
        return "".join(xml_node(name, item) for item in value)
    if not isinstance(value, dict):
        return f"<{name}>{escape(str(value))}</{name}>"
    attrs, children = [], []
    for key, item in value.items():
        if isinstance(item, (dict, list)):
            children.append(xml_node(key, item))
        else:
            text = str(item).lower() if isinstance(item, bool) else str(item)
            attrs.append(f" {key}={quoteattr(text)}")
    return f"<{name}{''.join(attrs)}>{''.join(children)}</{name}>" if children else f"<{name}{''.join(attrs)}/>"


def envelope(payload: dict, status: str = "ok") -> dict:
    return {"status": status, "version": API_VERSION, "type": "atena", "serverVersion": "3", "openSubsonic": True, **payload}


def render(payload: dict, fmt: str, callback: str = "", status: str = "ok") -> tuple[str, str]:
    body = envelope(payload, status)
    if fmt in ("json", "jsonp"):
        text = json.dumps({"subsonic-response": body}, ensure_ascii=False)
        if fmt == "jsonp" and callback.replace("_", "").replace(".", "").isalnum():
            return f"{callback}({text});", "application/javascript"
        return text, "application/json"
    inner = xml_node("subsonic-response", {**body, "xmlns": "http://subsonic.org/restapi"})
    return '<?xml version="1.0" encoding="UTF-8"?>' + inner, "text/xml"


def failure(code: int, message: str = "") -> dict:
    return {"error": {"code": code, "message": message or ERRORS.get(code, "Errore")}}
