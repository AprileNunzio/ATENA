import json
import logging
import time
from pathlib import Path

from features.music import catalog, layout, organizer
from features.music.db import db

log = logging.getLogger("atena.music")
MAX_TRACKS = 5000
SMART_FIELDS = {"genre": "genre=?", "artist": "artist_key=?", "year_from": "year>=?", "year_to": "year<=?", "album": "album_key=?"}
SMART_FLAGS = {"never_played": "plays=0", "played": "plays>0", "recent_days": "added>=?", "liked": "id IN (SELECT track_id FROM likes WHERE user=?)",
               "forgotten_days": "plays>0 AND last_played<?"}
SMART_SORTS = ("recent", "plays", "random", "title", "year", "played")


def listing(user: str) -> list[dict]:
    rows = db.rows("SELECT p.id, p.name, p.owner, p.kind, p.shared, p.updated, p.description, "
                   "(SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id=p.id) tracks, "
                   "(SELECT COALESCE(SUM(t.duration),0) FROM playlist_tracks pt JOIN tracks t ON t.id=pt.track_id WHERE pt.playlist_id=p.id) seconds, "
                   "(SELECT t.album_key FROM playlist_tracks pt JOIN tracks t ON t.id=pt.track_id WHERE pt.playlist_id=p.id ORDER BY pt.pos LIMIT 1) cover_key "
                   "FROM playlists p WHERE p.owner=? OR p.shared=1 ORDER BY p.updated DESC", (user,))
    for r in rows:
        r["mine"] = r["owner"] == user
    return rows


def get(playlist_id: int, user: str) -> dict | None:
    head = db.row("SELECT id, name, owner, kind, rule, shared, description, created, updated FROM playlists WHERE id=? AND (owner=? OR shared=1)",
                  (playlist_id, user))
    if not head:
        return None
    head["mine"] = head["owner"] == user
    if head["kind"] == "smart":
        head["tracks"] = smart_tracks(json.loads(head["rule"] or "{}"), user)
    else:
        ids = [r["track_id"] for r in db.rows("SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY pos", (playlist_id,))]
        head["tracks"] = catalog.by_ids(ids, user)
    head["seconds"] = round(sum(t["duration"] for t in head["tracks"]))
    return head


def owned(playlist_id: int, user: str) -> dict | None:
    return db.row("SELECT id, kind, owner FROM playlists WHERE id=? AND owner=?", (playlist_id, user))


def create(user: str, name: str, kind: str = "manual", rule: dict | None = None, description: str = "") -> int:
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("Serve un nome")
    if db.scalar("SELECT COUNT(*) FROM playlists WHERE owner=?", (user,)) >= 300:
        raise ValueError("Troppe playlist")
    now = time.time()
    clean = clean_rule(rule or {}) if kind == "smart" else {}
    return db.run("INSERT INTO playlists(name, owner, created, updated, kind, rule, description) VALUES(?,?,?,?,?,?,?)",
                  (name, user, now, now, "smart" if kind == "smart" else "manual", json.dumps(clean), description[:300]))


def rename(playlist_id: int, user: str, name: str, description: str | None = None, shared: bool | None = None, rule: dict | None = None) -> bool:
    row = owned(playlist_id, user)
    if not row or not (name or "").strip():
        return False
    db.run("UPDATE playlists SET name=?, updated=? WHERE id=?", (name.strip()[:80], time.time(), playlist_id))
    if description is not None:
        db.run("UPDATE playlists SET description=? WHERE id=?", (description[:300], playlist_id))
    if shared is not None:
        db.run("UPDATE playlists SET shared=? WHERE id=?", (int(bool(shared)), playlist_id))
    if rule is not None and row["kind"] == "smart":
        db.run("UPDATE playlists SET rule=? WHERE id=?", (json.dumps(clean_rule(rule)), playlist_id))
    return True


def delete(playlist_id: int, user: str) -> bool:
    if not owned(playlist_id, user):
        return False
    db.run("DELETE FROM playlist_tracks WHERE playlist_id=?", (playlist_id,))
    db.run("DELETE FROM playlists WHERE id=?", (playlist_id,))
    return True


def write_order(playlist_id: int, ids: list[int]) -> None:
    def work(conn):
        conn.execute("DELETE FROM playlist_tracks WHERE playlist_id=?", (playlist_id,))
        conn.executemany("INSERT INTO playlist_tracks(playlist_id, pos, track_id) VALUES(?,?,?)", [(playlist_id, i, t) for i, t in enumerate(ids)])
        conn.execute("UPDATE playlists SET updated=? WHERE id=?", (time.time(), playlist_id))
    db.transaction(work)


def current_ids(playlist_id: int) -> list[int]:
    return [r["track_id"] for r in db.rows("SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY pos", (playlist_id,))]


def add(playlist_id: int, user: str, track_ids: list[int]) -> int:
    row = owned(playlist_id, user)
    if not row or row["kind"] != "manual":
        raise ValueError("Playlist non modificabile")
    valid = [t.get("id") for t in catalog.by_ids(track_ids)]
    ids = current_ids(playlist_id) + [t for t in valid if t is not None]
    if len(ids) > MAX_TRACKS:
        raise ValueError("Playlist troppo lunga")
    write_order(playlist_id, ids)
    return len(valid)


def remove(playlist_id: int, user: str, positions: list[int]) -> bool:
    row = owned(playlist_id, user)
    if not row or row["kind"] != "manual":
        return False
    drop = {int(p) for p in positions if str(p).lstrip("-").isdigit()}
    write_order(playlist_id, [t for i, t in enumerate(current_ids(playlist_id)) if i not in drop])
    return True


def reorder(playlist_id: int, user: str, source: int, target: int) -> bool:
    row = owned(playlist_id, user)
    ids = current_ids(playlist_id) if row and row["kind"] == "manual" else []
    if not ids or not (0 <= source < len(ids)) or not (0 <= target < len(ids)):
        return False
    ids.insert(target, ids.pop(source))
    write_order(playlist_id, ids)
    return True


def clean_rule(rule: dict) -> dict:
    out: dict = {}
    for key in ("genre", "artist", "album"):
        if str(rule.get(key) or "").strip():
            out[key] = str(rule[key]).strip()[:80]
    for key in ("year_from", "year_to", "recent_days", "forgotten_days", "limit"):
        try:
            value = int(rule.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            out[key] = min(value, 100000 if key.startswith("year") else 3650 if key.endswith("days") else 500)
    for key in ("never_played", "played", "liked"):
        if rule.get(key):
            out[key] = True
    sort = str(rule.get("sort") or "recent")
    out["sort"] = sort if sort in SMART_SORTS else "recent"
    return out


def smart_tracks(rule: dict, user: str) -> list[dict]:
    rule = clean_rule(rule)
    where, params = [], []
    for key, clause in SMART_FIELDS.items():
        if key in rule:
            where.append(clause)
            params.append(rule[key])
    now = time.time()
    for key, clause in SMART_FLAGS.items():
        if key == "recent_days" and key in rule:
            where.append(clause)
            params.append(now - rule[key] * 86400)
        elif key == "forgotten_days" and key in rule:
            where.append(clause)
            params.append(now - rule[key] * 86400)
        elif key == "liked" and rule.get(key):
            where.append(clause)
            params.append(user)
        elif key in ("never_played", "played") and rule.get(key):
            where.append(clause)
    return catalog.tracks(rule["sort"], rule.get("limit", 100), 0, user, " AND ".join(where), tuple(params))


def m3u(playlist: dict) -> str:
    lines = ["#EXTM3U", f"#PLAYLIST:{playlist['name']}"]
    for t in playlist["tracks"]:
        row = db.row("SELECT path FROM tracks WHERE id=?", (t["id"],))
        if not row:
            continue
        lines.append(f"#EXTINF:{int(t['duration'])},{t['artist']} - {t['title']}")
        lines.append(f"../{row['path']}")
    return "\n".join(lines) + "\n"


def export(playlist_id: int, user: str) -> Path | None:
    playlist = get(playlist_id, user)
    if not playlist:
        return None
    target = layout.playlists() / f"{organizer.name(playlist['name'], 'Playlist')}.m3u8"
    try:
        target.write_text(m3u(playlist), encoding="utf-8")
    except OSError as exc:
        log.warning("Playlist non esportata: %s", exc)
        return None
    return target
