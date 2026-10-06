import time

from features.music import catalog, conf
from features.music.db import db

MIN_PLAYED = 20.0


def like(user: str, track_id: int, on: bool) -> bool:
    if not catalog.track(track_id):
        return False
    if on:
        db.run("INSERT OR IGNORE INTO likes(user, track_id, at) VALUES(?,?,?)", (user, track_id, time.time()))
    else:
        db.run("DELETE FROM likes WHERE user=? AND track_id=?", (user, track_id))
    return True


def rate(user: str, track_id: int, stars: int) -> bool:
    if not catalog.track(track_id):
        return False
    stars = max(0, min(5, int(stars)))
    if stars == 0:
        db.run("DELETE FROM ratings WHERE user=? AND track_id=?", (user, track_id))
    else:
        db.run("INSERT INTO ratings(user, track_id, stars) VALUES(?,?,?) ON CONFLICT(user, track_id) DO UPDATE SET stars=excluded.stars",
               (user, track_id, stars))
    return True


def liked(user: str, limit=200, offset=0) -> list[dict]:
    where = "id IN (SELECT track_id FROM likes WHERE user=?)"
    return catalog.tracks("recent", limit, offset, user, where, (user,))


def played(user: str, track_id: int, seconds: float, done: bool, source: str = "") -> bool:
    track = catalog.track(track_id)
    if not track:
        return False
    seconds = max(0.0, min(float(seconds or 0), float(track["duration"] or seconds or 0) + 5))
    counted = done or seconds >= min(MIN_PLAYED, float(track["duration"] or MIN_PLAYED) * 0.5)
    now = time.time()
    if counted:
        db.run("UPDATE tracks SET plays=plays+1, last_played=? WHERE id=?", (now, track_id))
        db.run("INSERT INTO history(user, track_id, at, secs, done, source) VALUES(?,?,?,?,?,?)",
               (user, track_id, now, seconds, int(done), source[:20]))
    return counted


def recent(user: str, limit=50) -> list[dict]:
    rows = db.rows("SELECT track_id, MAX(at) at FROM history WHERE user=? GROUP BY track_id ORDER BY at DESC LIMIT ?", (user, catalog.clamp(limit)))
    order = {r["track_id"]: r["at"] for r in rows}
    found = catalog.by_ids(list(order), user)
    for t in found:
        t["played_at"] = order[t["id"]]
    return found


def top(user: str, days: int = 30, limit: int = 20) -> list[dict]:
    since = time.time() - days * 86400
    rows = db.rows("SELECT track_id, COUNT(*) n FROM history WHERE user=? AND at>=? GROUP BY track_id ORDER BY n DESC LIMIT ?",
                   (user, since, catalog.clamp(limit)))
    counts = {r["track_id"]: r["n"] for r in rows}
    found = catalog.by_ids(list(counts), user)
    for t in found:
        t["recent_plays"] = counts[t["id"]]
    return found


def summary(user: str, days: int = 30) -> dict:
    since = time.time() - days * 86400
    head = db.row("SELECT COUNT(*) plays, COALESCE(SUM(secs),0) seconds, COUNT(DISTINCT track_id) tracks FROM history WHERE user=? AND at>=?",
                  (user, since)) or {}
    artists = db.rows("SELECT t.artist artist, COUNT(*) n, SUM(h.secs) seconds FROM history h JOIN tracks t ON t.id=h.track_id "
                      "WHERE h.user=? AND h.at>=? GROUP BY t.artist_key ORDER BY n DESC LIMIT 8", (user, since))
    genres = db.rows("SELECT t.genre genre, COUNT(*) n FROM history h JOIN tracks t ON t.id=h.track_id "
                     "WHERE h.user=? AND h.at>=? AND t.genre<>'' GROUP BY t.genre ORDER BY n DESC LIMIT 6", (user, since))
    hours = db.rows("SELECT CAST(strftime('%H', at, 'unixepoch', 'localtime') AS INTEGER) hour, COUNT(*) n FROM history "
                    "WHERE user=? AND at>=? GROUP BY hour ORDER BY hour", (user, since))
    return {"days": days, **head, "artists": artists, "genres": genres, "hours": hours, "top": top(user, days, 10)}


def prune() -> int:
    cutoff = time.time() - conf.history_days() * 86400
    return db.run("DELETE FROM history WHERE at<?", (cutoff,))
