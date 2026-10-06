import random
import time
from itertools import zip_longest

from features.music import catalog, listening
from features.music.db import db

MIX_SIZE = 50
KINDS = ("artist", "genre", "decade", "rediscover", "unheard", "liked", "recent", "random")


def favourite_artists(user: str, limit: int = 4) -> list[dict]:
    since = time.time() - 90 * 86400
    rows = db.rows("SELECT t.artist_key key, t.artist name, MIN(t.id) cover_id, MAX(t.album_key) album_key, COUNT(*) n FROM history h "
                   "JOIN tracks t ON t.id=h.track_id WHERE h.user=? AND h.at>=? GROUP BY t.artist_key ORDER BY n DESC LIMIT ?", (user, since, limit))
    if rows:
        return rows
    return db.rows("SELECT artist_key key, artist name, MIN(id) cover_id, MAX(album_key) album_key, SUM(plays) n FROM tracks "
                   "GROUP BY artist_key ORDER BY n DESC, COUNT(*) DESC LIMIT ?", (limit,))


def favourite_genres(user: str, limit: int = 3) -> list[dict]:
    since = time.time() - 90 * 86400
    rows = db.rows("SELECT t.genre name, MAX(t.album_key) album_key, COUNT(*) n FROM history h JOIN tracks t ON t.id=h.track_id "
                   "WHERE h.user=? AND h.at>=? AND t.genre<>'' GROUP BY t.genre ORDER BY n DESC LIMIT ?", (user, since, limit))
    return rows or db.rows("SELECT genre name, MAX(album_key) album_key, COUNT(*) n FROM tracks WHERE genre<>'' GROUP BY genre ORDER BY n DESC LIMIT ?", (limit,))


def descriptors(user: str) -> list[dict]:
    out = []
    for a in favourite_artists(user):
        out.append({"id": f"artist:{a['key']}", "title": f"Mix {a['name']}", "subtitle": "Dal tuo ascolto", "cover_key": a["album_key"]})
    for g in favourite_genres(user):
        out.append({"id": f"genre:{g['name']}", "title": f"Mix {g['name']}", "subtitle": "Il tuo genere", "cover_key": g["album_key"]})
    for d in catalog.decades()[:3]:
        cover = db.row("SELECT album_key FROM tracks WHERE year>=? AND year<? ORDER BY RANDOM() LIMIT 1", (d["decade"], d["decade"] + 10))
        out.append({"id": f"decade:{d['decade']}", "title": f"Anni {str(d['decade'])[2:] if d['decade'] < 2000 else d['decade']}", "subtitle": f"{d['tracks']} brani",
                    "cover_key": (cover or {}).get("album_key", "")})
    special = [("rediscover", "Riscoperta", "Brani che non ascolti da tempo"), ("unheard", "Mai ascoltati", "Tutto quello che non hai ancora provato"),
               ("liked", "I tuoi preferiti", "Mescolati"), ("recent", "Novità", "Appena aggiunti")]
    for kind, title, subtitle in special:
        sample = mix(kind, user, 1)
        out.append({"id": kind, "title": title, "subtitle": subtitle, "cover_key": sample[0]["album_key"] if sample else ""})
    return [m for m in out if m["cover_key"] or m["id"] in ("liked",)]


def mix(identifier: str, user: str, limit: int = MIX_SIZE) -> list[dict]:
    kind, _, value = identifier.partition(":")
    if kind not in KINDS:
        return []
    now = time.time()
    where, params, sort = "", (), "random"
    if kind == "artist":
        similar = db.row("SELECT genre FROM tracks WHERE artist_key=? AND genre<>'' LIMIT 1", (value,))
        where = "artist_key=? OR (genre=? AND genre<>'')" if similar else "artist_key=?"
        params = (value, similar["genre"]) if similar else (value,)
    elif kind == "genre":
        where, params = "genre=?", (value,)
    elif kind == "decade":
        try:
            start = int(value)
        except ValueError:
            return []
        where, params = "year>=? AND year<?", (start, start + 10)
    elif kind == "rediscover":
        where, params = "plays>0 AND last_played<?", (now - 60 * 86400,)
    elif kind == "unheard":
        where = "plays=0"
    elif kind == "liked":
        where, params = "id IN (SELECT track_id FROM likes WHERE user=?)", (user,)
    elif kind == "recent":
        where, params, sort = "added>=?", (now - 30 * 86400,), "recent"
    pool = catalog.tracks(sort, 400, 0, user, where, params)
    if kind == "artist":
        head = [t for t in pool if t["artist_key"] == value]
        rest = [t for t in pool if t["artist_key"] != value]
        random.shuffle(head)
        random.shuffle(rest)
        pool = [x for pair in zip_longest(head, rest) for x in pair if x is not None]
    elif sort == "random":
        random.shuffle(pool)
    return pool[:limit]


def similar(seed_id: int, user: str, exclude: list[int], limit: int = 15) -> list[dict]:
    seed = catalog.track(seed_id)
    if not seed:
        return []
    skip = {int(i) for i in exclude if str(i).lstrip("-").isdigit()} | {seed_id}
    recent_ids = {r["track_id"] for r in db.rows("SELECT DISTINCT track_id FROM history WHERE user=? AND at>=?", (user, time.time() - 3 * 3600))}
    rows = db.rows(
        f"SELECT {catalog.COLUMNS}, "
        "((artist_key=?)*3 + (genre=? AND genre<>'')*2 + (album_key=?)*1 + (ABS(year-?)<=8 AND year>0)*1 "
        " + (id IN (SELECT track_id FROM likes WHERE user=?))*1) AS score FROM tracks WHERE id<>? ORDER BY score DESC, RANDOM() LIMIT 300",
        (seed["artist_key"], seed["genre"], seed["album_key"], seed["year"], user, seed_id))
    pool = [r for r in rows if r["id"] not in skip and r["id"] not in recent_ids]
    tiers: dict = {}
    for r in pool:
        tiers.setdefault(r["score"], []).append(r)
    top = []
    for score in sorted(tiers, reverse=True):
        random.shuffle(tiers[score])
        top += tiers[score]
    return catalog.decorate(top[:limit], user)


def home(user: str) -> dict:
    return {"recent": listening.recent(user, 12), "added": catalog.albums("recent", 12), "random": catalog.albums("random", 12),
            "popular": catalog.tracks("plays", 12, 0, user, "plays>0"), "mixes": descriptors(user), "stats": catalog.stats()}
