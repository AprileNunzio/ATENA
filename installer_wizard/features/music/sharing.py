import secrets
import time

from features.music import catalog, conf, playlists
from features.music.db import db

KINDS = ("track", "album", "playlist")
MAX_ACTIVE = 200
FAIL_WINDOW = 60.0
FAIL_LIMIT = 30
_failures: dict[str, list[float]] = {}


def create(user: str, kind: str, ref: str, hours: float | None = None) -> dict:
    if not conf.share_links():
        raise ValueError("I collegamenti condivisi sono disattivati nelle impostazioni")
    if kind not in KINDS or not str(ref).strip():
        raise ValueError("Elemento non condivisibile")
    if not tracks_of(kind, str(ref), user):
        raise ValueError("Niente da condividere")
    if db.scalar("SELECT COUNT(*) FROM shares WHERE owner=? AND expires>?", (user, time.time())) >= MAX_ACTIVE:
        raise ValueError("Troppi collegamenti attivi: revoca quelli vecchi")
    span = max(1.0, min(720.0, float(hours or conf.share_hours())))
    token = secrets.token_urlsafe(18)
    now = time.time()
    db.run("INSERT INTO shares(token, kind, ref, owner, created, expires) VALUES(?,?,?,?,?,?)", (token, kind, str(ref), user, now, now + span * 3600))
    return {"token": token, "expires": now + span * 3600}


def tracks_of(kind: str, ref: str, user: str) -> list[dict]:
    if kind == "track":
        found = catalog.by_ids([ref])
        return found
    if kind == "album":
        album = catalog.album(ref)
        return album["tracks"] if album else []
    try:
        playlist = playlists.get(int(ref), user)
    except ValueError:
        return []
    return playlist["tracks"] if playlist else []


def throttled(client: str) -> bool:
    now = time.time()
    hits = [t for t in _failures.get(client, []) if now - t < FAIL_WINDOW]
    _failures[client] = hits
    if len(_failures) > 2000:
        _failures.clear()
    return len(hits) >= FAIL_LIMIT


def failed(client: str) -> None:
    _failures.setdefault(client, []).append(time.time())


def lookup(token: str) -> dict | None:
    row = db.row("SELECT token, kind, ref, owner, created, expires, uses FROM shares WHERE token=?", (token[:40],))
    if not row or row["expires"] < time.time():
        return None
    return row


def resolve(token: str) -> dict | None:
    row = lookup(token)
    if not row:
        return None
    found = tracks_of(row["kind"], row["ref"], row["owner"])
    if not found:
        return None
    title = {"track": found[0]["title"], "album": found[0]["album"]}.get(row["kind"])
    if row["kind"] == "playlist":
        playlist = playlists.get(int(row["ref"]), row["owner"])
        title = playlist["name"] if playlist else "Playlist"
    return {**row, "title": title, "tracks": [{k: t[k] for k in ("id", "title", "artist", "album", "duration", "album_key", "cover")} for t in found]}


def touch(token: str) -> None:
    db.run("UPDATE shares SET uses=uses+1 WHERE token=?", (token[:40],))


def listing(user: str) -> list[dict]:
    return db.rows("SELECT token, kind, ref, created, expires, uses FROM shares WHERE owner=? AND expires>? ORDER BY created DESC", (user, time.time()))


def revoke(user: str, token: str) -> bool:
    return db.run("DELETE FROM shares WHERE token=? AND owner=?", (token[:40], user)) > 0


def purge() -> int:
    return db.run("DELETE FROM shares WHERE expires<?", (time.time() - 86400,))
