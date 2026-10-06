import hashlib
import re
import time

from features.music.db import db

SORTS = {"recent": "added DESC", "title": "title COLLATE NOCASE", "artist": "artist COLLATE NOCASE, album COLLATE NOCASE, disc_no, track_no",
         "album": "album COLLATE NOCASE, disc_no, track_no", "year": "year DESC, album COLLATE NOCASE", "plays": "plays DESC",
         "played": "last_played DESC", "duration": "duration DESC", "random": "RANDOM()"}
COLUMNS = ("id, title, artist, album_artist, album, track_no, disc_no, year, genre, duration, bitrate, cover, album_key, artist_key, "
           "added, plays, last_played")
TOKEN = re.compile(r"[\w']+", re.U)


def key(*parts: str) -> str:
    return hashlib.sha1("|".join(p.strip().lower() for p in parts).encode("utf-8")).hexdigest()[:12]


def clamp(limit, default: int = 50, top: int = 500) -> int:
    try:
        return max(1, min(top, int(limit)))
    except (TypeError, ValueError):
        return default


def offset_of(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def decorate(rows: list[dict], user: str) -> list[dict]:
    if not rows or not user:
        return rows
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    liked = {r["track_id"] for r in db.rows(f"SELECT track_id FROM likes WHERE user=? AND track_id IN ({marks})", (user, *ids))}
    stars = {r["track_id"]: r["stars"] for r in db.rows(f"SELECT track_id, stars FROM ratings WHERE user=? AND track_id IN ({marks})", (user, *ids))}
    for r in rows:
        r["liked"] = r["id"] in liked
        r["stars"] = stars.get(r["id"], 0)
    return rows


def tracks(sort: str = "recent", limit=50, offset=0, user: str = "", where: str = "", params: tuple = ()) -> list[dict]:
    order = SORTS.get(sort, SORTS["recent"])
    clause = f"WHERE {where}" if where else ""
    sql = f"SELECT {COLUMNS} FROM tracks {clause} ORDER BY {order} LIMIT ? OFFSET ?"
    return decorate(db.rows(sql, (*params, clamp(limit), offset_of(offset))), user)


def track(track_id: int, user: str = "") -> dict | None:
    rows = db.rows(f"SELECT {COLUMNS}, path FROM tracks WHERE id=?", (track_id,))
    return decorate(rows, user)[0] if rows else None


def by_ids(ids: list[int], user: str = "") -> list[dict]:
    ids = [int(i) for i in ids if str(i).lstrip("-").isdigit()][:1000]
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    found = {r["id"]: r for r in db.rows(f"SELECT {COLUMNS} FROM tracks WHERE id IN ({marks})", tuple(ids))}
    return decorate([found[i] for i in ids if i in found], user)


def match_query(text: str) -> str:
    words = TOKEN.findall(text.lower())[:8]
    return " ".join(f'"{w}"*' for w in words)


def search(text: str, limit=40, user: str = "") -> dict:
    text = (text or "").strip()[:80]
    if not text:
        return {"tracks": [], "albums": [], "artists": []}
    limit = clamp(limit, 40, 200)
    if db.fts and match_query(text):
        found = db.rows(f"SELECT {COLUMNS} FROM tracks WHERE id IN (SELECT rowid FROM tracks_fts WHERE tracks_fts MATCH ? ORDER BY rank LIMIT ?)",
                        (match_query(text), limit))
    else:
        found = db.rows(f"SELECT {COLUMNS} FROM tracks WHERE lower(title||' '||artist||' '||album) LIKE ? LIMIT ?", (f"%{text.lower()}%", limit))
    words = [f"%{w}%" for w in TOKEN.findall(text.lower())[:6]] or [f"%{text.lower()}%"]
    album_where = " AND ".join("lower(album||' '||album_artist) LIKE ?" for _ in words)
    artist_where = " AND ".join("lower(artist) LIKE ?" for _ in words)
    albums = db.rows("SELECT album_key, album, album_artist, MAX(year) year, COUNT(*) tracks, MIN(id) cover_id, MAX(cover) cover FROM tracks "
                     f"WHERE {album_where} GROUP BY album_key ORDER BY album COLLATE NOCASE LIMIT 12", tuple(words))
    artists = db.rows("SELECT artist_key, artist, COUNT(*) tracks, COUNT(DISTINCT album_key) albums FROM tracks "
                      f"WHERE {artist_where} GROUP BY artist_key ORDER BY tracks DESC LIMIT 12", tuple(words))
    return {"tracks": decorate(found, user), "albums": albums, "artists": artists}


def albums(sort: str = "title", limit=60, offset=0, genre: str = "", year: int = 0) -> list[dict]:
    order = {"title": "album COLLATE NOCASE", "artist": "album_artist COLLATE NOCASE, album COLLATE NOCASE", "recent": "added DESC",
             "year": "year DESC", "random": "RANDOM()", "plays": "plays DESC"}.get(sort, "album COLLATE NOCASE")
    where, params = [], []
    if genre:
        where.append("genre=?")
        params.append(genre)
    if year:
        where.append("year=?")
        params.append(int(year))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = (f"SELECT album_key, album, album_artist, MAX(year) year, COUNT(*) tracks, SUM(duration) duration, MIN(id) cover_id, MAX(cover) cover, "
           f"MAX(added) added, SUM(plays) plays FROM tracks {clause} GROUP BY album_key ORDER BY {order} LIMIT ? OFFSET ?")
    return db.rows(sql, (*params, clamp(limit, 60), offset_of(offset)))


def album(album_key: str, user: str = "") -> dict | None:
    rows = tracks("album", 500, 0, user, "album_key=?", (album_key,))
    if not rows:
        return None
    first = rows[0]
    return {"album_key": album_key, "album": first["album"], "album_artist": first["album_artist"],
            "year": max(r["year"] for r in rows), "duration": round(sum(r["duration"] for r in rows)), "cover_id": first["id"],
            "cover": any(r["cover"] for r in rows), "tracks": rows}


def artists(limit=200, offset=0) -> list[dict]:
    return db.rows("SELECT artist_key, artist, COUNT(*) tracks, COUNT(DISTINCT album_key) albums, MIN(id) cover_id, MAX(cover) cover, MAX(album_key) album_key, SUM(plays) plays "
                   "FROM tracks GROUP BY artist_key ORDER BY artist COLLATE NOCASE LIMIT ? OFFSET ?", (clamp(limit, 200, 1000), offset_of(offset)))


def artist(artist_key: str, user: str = "") -> dict | None:
    head = db.row("SELECT artist, COUNT(*) tracks, SUM(duration) duration, SUM(plays) plays FROM tracks WHERE artist_key=?", (artist_key,))
    if not head or not head["tracks"]:
        return None
    popular = tracks("plays", 10, 0, user, "artist_key=?", (artist_key,))
    albums_ = db.rows("SELECT album_key, album, album_artist, MAX(year) year, COUNT(*) tracks, MIN(id) cover_id, MAX(cover) cover FROM tracks "
                      "WHERE artist_key=? GROUP BY album_key ORDER BY year DESC", (artist_key,))
    return {"artist_key": artist_key, **head, "popular": popular, "albums": albums_}


def genres() -> list[dict]:
    return db.rows("SELECT genre, COUNT(*) tracks, COUNT(DISTINCT album_key) albums FROM tracks WHERE genre<>'' GROUP BY genre ORDER BY tracks DESC")


def decades() -> list[dict]:
    return db.rows("SELECT (year/10)*10 decade, COUNT(*) tracks FROM tracks WHERE year>1900 GROUP BY decade ORDER BY decade DESC")


def stats() -> dict:
    head = db.row("SELECT COUNT(*) tracks, COUNT(DISTINCT album_key) albums, COUNT(DISTINCT artist_key) artists, COALESCE(SUM(duration),0) seconds, "
                  "COALESCE(SUM(size),0) bytes FROM tracks") or {}
    head["playlists"] = db.scalar("SELECT COUNT(*) FROM playlists")
    head["updated"] = db.scalar("SELECT MAX(added) FROM tracks")
    head["now"] = time.time()
    return head
