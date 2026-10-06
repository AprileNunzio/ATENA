import asyncio
import hashlib
import hmac
import re
import time
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from features.music import catalog, conf, covers, layout, listening, mixes, playlists, scanner, stream
from features.music import subsonic_fmt as fmt
from features.music.db import db
from features.music.service import library
from features.music.sharing import failed, throttled

public_routes = APIRouter()
USER_RE = re.compile(r"[^A-Za-z0-9_.@-]")
LIST_TYPES = {"newest": "recent", "alphabeticalByName": "title", "alphabeticalByArtist": "artist", "random": "random", "frequent": "plays",
              "byYear": "year", "recent": "recent", "highest": "plays"}


class Params:

    def __init__(self, items: list[tuple[str, str]]) -> None:
        self.items = items

    def get(self, key: str, default: str = "") -> str:
        return next((v for k, v in self.items if k == key), default)

    def all(self, key: str) -> list[str]:
        return [v for k, v in self.items if k == key]

    def number(self, key: str, default: int = 0, lo: int = 0, hi: int = 500) -> int:
        try:
            return max(lo, min(hi, int(self.get(key, str(default)))))
        except ValueError:
            return default


class Refusal(Exception):
    def __init__(self, code: int, message: str = "") -> None:
        self.code, self.message = code, message


def password_ok(params: Params, secret: str) -> bool:
    given = params.get("p")
    if given:
        if given.startswith("enc:"):
            try:
                given = bytes.fromhex(given[4:]).decode("utf-8")
            except ValueError:
                return False
        return hmac.compare_digest(given.encode("utf-8"), secret.encode("utf-8"))
    token, salt = params.get("t"), params.get("s")
    return bool(token and salt) and hmac.compare_digest(hashlib.md5((secret + salt).encode("utf-8")).hexdigest(), token.lower())


def identify(params: Params, client: str) -> str:
    secret = conf.app_password()
    if not conf.subsonic_enabled() or len(secret) < 8:
        raise Refusal(50, "Il server per le app non è attivo")
    if throttled(client):
        raise Refusal(40, "Troppi tentativi")
    user = USER_RE.sub("", params.get("u"))[:32]
    if not user or not password_ok(params, secret):
        failed(client)
        raise Refusal(40)
    return user.lower()


def need_id(params: Params, key: str = "id") -> str:
    value = params.get(key)
    if not value:
        raise Refusal(10)
    return value


def key_of(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


async def ping(p, user):
    return {}


async def get_license(p, user):
    return {"license": {"valid": True, "email": "atena@local", "licenseExpires": "2099-12-31T00:00:00.000Z"}}


async def extensions(p, user):
    return {"openSubsonicExtensions": []}


async def folders(p, user):
    return {"musicFolders": {"musicFolder": [{"id": 1, "name": "Musica"}]}}


async def get_artists(p, user):
    rows = catalog.artists(1000)
    index: dict = {}
    for row in rows:
        letter = row["artist"][:1].upper()
        index.setdefault(letter if letter.isalpha() else "#", []).append(fmt.artist(row))
    return {"artists": {"ignoredArticles": "", "index": [{"name": k, "artist": v} for k, v in sorted(index.items())]}}


async def get_indexes(p, user):
    result = await get_artists(p, user)
    result["indexes"] = result.pop("artists")
    result["indexes"]["lastModified"] = int(time.time() * 1000)
    return result


async def get_artist(p, user):
    found = catalog.artist(key_of(need_id(p), "ar-"), user)
    if not found:
        raise Refusal(70)
    albums = [fmt.album({**a, "duration": 0}) for a in found["albums"]]
    return {"artist": {"id": f"ar-{found['artist_key']}", "name": found["artist"], "albumCount": len(albums), "album": albums}}


async def get_album(p, user):
    found = catalog.album(key_of(need_id(p), "al-"), user)
    if not found:
        raise Refusal(70)
    head = fmt.album({"album_key": found["album_key"], "album": found["album"], "album_artist": found["album_artist"], "tracks": len(found["tracks"]),
                      "duration": found["duration"], "year": found["year"], "cover": found["cover"], "added": found["tracks"][0]["added"]})
    return {"album": {**head, "song": fmt.songs(found["tracks"], user)}}


async def get_song(p, user):
    try:
        found = catalog.by_ids([int(need_id(p))], user)
    except ValueError:
        raise Refusal(70)
    if not found:
        raise Refusal(70)
    return {"song": fmt.songs(found, user)[0]}


async def album_list(p, user):
    kind = p.get("type", "newest")
    size, offset = p.number("size", 20), p.number("offset", 0, 0, 100000)
    if kind == "starred":
        rows = db.rows("SELECT album_key, album, album_artist, MAX(year) year, COUNT(*) tracks, SUM(duration) duration, MAX(cover) cover, MAX(added) added "
                       "FROM tracks WHERE id IN (SELECT track_id FROM likes WHERE user=?) GROUP BY album_key LIMIT ? OFFSET ?", (user, size, offset))
    else:
        sort = LIST_TYPES.get(kind, "title")
        genre = p.get("genre") if kind == "byGenre" else ""
        rows = catalog.albums(sort if kind != "byGenre" else "title", size, offset, genre, p.number("fromYear", 0, 0, 9999) if kind == "byYear" else 0)
    return {"albumList2": {"album": [fmt.album(r) for r in rows]}}


async def random_songs(p, user):
    genre = p.get("genre")
    rows = catalog.tracks("random", p.number("size", 10), 0, user, "genre=?" if genre else "", (genre,) if genre else ())
    return {"randomSongs": {"song": fmt.songs(rows, user)}}


async def by_genre(p, user):
    rows = catalog.tracks("title", p.number("count", 10), p.number("offset", 0, 0, 100000), user, "genre=?", (p.get("genre"),))
    return {"songsByGenre": {"song": fmt.songs(rows, user)}}


async def genres(p, user):
    return {"genres": {"genre": [{"value": g["genre"], "songCount": g["tracks"], "albumCount": g["albums"]} for g in catalog.genres()]}}


async def search(p, user):
    found = catalog.search(p.get("query").strip('"*'), 60, user)
    songs = found["tracks"][p.number("songOffset", 0, 0, 1000):][:p.number("songCount", 20)]
    albums = [fmt.album({**a, "duration": 0, "added": 0}) for a in found["albums"][:p.number("albumCount", 20)]]
    artists = [fmt.artist(a) for a in found["artists"][:p.number("artistCount", 20)]]
    return {"searchResult3": {"artist": artists, "album": albums, "song": fmt.songs(songs, user)}}


async def starred(p, user):
    return {"starred2": {"song": fmt.songs(listening.liked(user, 500), user)}}


async def star(p, user, on=True):
    for value in p.all("id"):
        if value.isdigit():
            listening.like(user, int(value), on)
    for value in p.all("albumId"):
        album = catalog.album(key_of(value, "al-"))
        for t in (album or {"tracks": []})["tracks"]:
            listening.like(user, t["id"], on)
    return {}


async def unstar(p, user):
    return await star(p, user, False)


async def scrobble(p, user):
    if p.get("submission", "true") != "false":
        for value in p.all("id"):
            if value.isdigit():
                found = catalog.track(int(value))
                if found:
                    listening.played(user, found["id"], found["duration"] or 60, True, "app")
    return {}


async def get_playlists(p, user):
    rows = playlists.listing(user)
    return {"playlists": {"playlist": [{"id": f"pl-{r['id']}", "name": r["name"], "owner": r["owner"], "public": bool(r["shared"]), "songCount": r["tracks"],
                                        "duration": int(r["seconds"]), "created": fmt.iso(r["updated"]), "changed": fmt.iso(r["updated"])} for r in rows]}}


def playlist_id(p: Params, key: str = "id") -> int:
    try:
        return int(key_of(need_id(p, key), "pl-"))
    except ValueError:
        raise Refusal(70)


async def get_playlist(p, user):
    found = playlists.get(playlist_id(p), user)
    if not found:
        raise Refusal(70)
    return {"playlist": {"id": f"pl-{found['id']}", "name": found["name"], "owner": found["owner"], "public": bool(found["shared"]),
                         "songCount": len(found["tracks"]), "duration": int(found["seconds"]), "entry": fmt.songs(found["tracks"], user)}}


async def create_playlist(p, user):
    ids = [int(i) for i in p.all("songId") if i.isdigit()]
    if p.get("playlistId"):
        target = playlist_id(p, "playlistId")
        if not playlists.owned(target, user):
            raise Refusal(50)
        playlists.write_order(target, ids)
    else:
        try:
            target = playlists.create(user, p.get("name") or "Playlist")
            playlists.add(target, user, ids)
        except ValueError as exc:
            raise Refusal(0, str(exc))
    return await get_playlist(Params([("id", f"pl-{target}")]), user)


async def update_playlist(p, user):
    target = playlist_id(p, "playlistId")
    if not playlists.owned(target, user):
        raise Refusal(50)
    if p.get("name"):
        playlists.rename(target, user, p.get("name"), p.get("comment") or None, p.get("public") == "true" if p.get("public") else None)
    removals = [int(i) for i in p.all("songIndexToRemove") if i.isdigit()]
    if removals:
        playlists.remove(target, user, removals)
    additions = [int(i) for i in p.all("songIdToAdd") if i.isdigit()]
    if additions:
        playlists.add(target, user, additions)
    return {}


async def delete_playlist(p, user):
    if not playlists.delete(playlist_id(p), user):
        raise Refusal(70)
    return {}


async def get_user(p, user):
    return {"user": {"username": user, "email": "", "scrobblingEnabled": True, "adminRole": False, "settingsRole": False, "downloadRole": True,
                     "uploadRole": False, "playlistRole": True, "coverArtRole": False, "commentRole": False, "podcastRole": False,
                     "streamRole": True, "jukeboxRole": False, "shareRole": False}}


async def now_playing(p, user):
    return {"nowPlaying": {}}


async def scan_status(p, user):
    return {"scanStatus": {"scanning": scanner.progress["running"], "count": scanner.progress["done"]}}


async def start_scan(p, user):
    library.trigger()
    return await scan_status(p, user)


async def similar(p, user):
    try:
        seed = int(need_id(p))
    except ValueError:
        raise Refusal(70)
    rows = await asyncio.to_thread(mixes.similar, seed, user, [], p.number("count", 20))
    return {"similarSongs2": {"song": fmt.songs(rows, user)}}


HANDLERS = {"ping": ping, "getLicense": get_license, "getOpenSubsonicExtensions": extensions, "getMusicFolders": folders,
            "getArtists": get_artists, "getIndexes": get_indexes, "getArtist": get_artist, "getAlbum": get_album, "getSong": get_song,
            "getAlbumList2": album_list, "getAlbumList": album_list, "getRandomSongs": random_songs, "getSongsByGenre": by_genre,
            "getGenres": genres, "search3": search, "search2": search, "getStarred2": starred, "getStarred": starred, "star": star,
            "unstar": unstar, "scrobble": scrobble, "getPlaylists": get_playlists, "getPlaylist": get_playlist,
            "createPlaylist": create_playlist, "updatePlaylist": update_playlist, "deletePlaylist": delete_playlist, "getUser": get_user,
            "getNowPlaying": now_playing, "getScanStatus": scan_status, "startScan": start_scan, "getSimilarSongs2": similar,
            "getSimilarSongs": similar}


def reply(payload: dict, params: Params, status: str = "ok") -> Response:
    text, media = fmt.render(payload, params.get("f", "xml"), params.get("callback"), status)
    return Response(text, media_type=media, headers={"Cache-Control": "no-store"})


async def binary(name: str, params: Params, request: Request) -> Response:
    value = need_id(params)
    if name in ("stream", "download"):
        found = db.row("SELECT path FROM tracks WHERE id=?", (int(value),)) if value.isdigit() else None
        if not found:
            raise Refusal(70)
        return stream.serve(layout.root() / found["path"], request, "mp3" if params.get("format") == "mp3" else "")
    key = key_of(value, "al-") if value.startswith("al-") else key_of(value, "ar-")
    if value.startswith("ar-"):
        row = db.row("SELECT album_key FROM tracks WHERE artist_key=? ORDER BY cover DESC LIMIT 1", (key,))
        key = row["album_key"] if row else key
    elif value.isdigit():
        row = db.row("SELECT album_key FROM tracks WHERE id=?", (int(value),))
        key = row["album_key"] if row else key
    data = await asyncio.to_thread(covers.thumbnail, key[:24], params.number("size", 300, 32, 1200))
    if data is None:
        raise Refusal(70)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@public_routes.api_route("/rest/{method}", methods=["GET", "POST"])
async def endpoint(method: str, request: Request):
    name = method[:-5] if method.endswith(".view") else method
    items = list(request.query_params.multi_items())
    if request.method == "POST":
        items += parse_qsl((await request.body()).decode("utf-8", errors="replace"), keep_blank_values=True)
    params = Params(items)
    client = request.client.host if request.client else "?"
    try:
        user = identify(params, client)
        if name in ("stream", "download", "getCoverArt"):
            return await binary(name, params, request)
        handler = HANDLERS.get(name)
        if handler is None:
            raise Refusal(0, "Metodo non supportato")
        return reply(await handler(params, user), params)
    except Refusal as refusal:
        return reply(fmt.failure(refusal.code, refusal.message), params, "failed")
    except HTTPException as exc:
        return reply(fmt.failure(0, str(exc.detail)), params, "failed")
