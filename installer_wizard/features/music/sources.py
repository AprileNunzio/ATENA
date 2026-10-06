import logging
import re

import httpx

log = logging.getLogger("atena.music")
USER_AGENT = "AtenaOS/3 (+https://github.com/AprileNunzio/ATENA)"
BRACKETS = re.compile(r"\(.*?\)|\[.*?\]|\{.*?\}")
NOISE = re.compile(r"\b(official|video|audio|lyrics?|lyric video|hd|hq|4k|remaster(?:ed)?|live|clip|ufficiale|testo|full album|mp3|320kbps)\b", re.I)
LIMIT = 6


def clean_query(text: str) -> str:
    plain = NOISE.sub(" ", BRACKETS.sub(" ", str(text or "")))
    return re.sub(r"\s+", " ", re.sub(r"[_]+", " ", plain)).strip(" -.")


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", BRACKETS.sub(" ", str(text or "").lower())))


def match(title: str, artist: str, found_title: str, found_artist: str) -> bool:
    wanted_title, wanted_artist = words(title), words(artist)
    return bool(wanted_title) and bool(wanted_artist) and wanted_title <= words(found_title) and wanted_artist <= words(found_artist)


def year_of(text) -> int:
    head = str(text or "")[:4]
    return int(head) if head.isdigit() else 0


async def get_json(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    try:
        reply = await client.get(url, params=params)
        return reply.json() if reply.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return {}


async def itunes(client, title: str, artist: str) -> dict | None:
    data = await get_json(client, "https://itunes.apple.com/search", {"term": f"{artist} {title}", "entity": "song", "limit": LIMIT, "country": "it"})
    for r in data.get("results", []):
        if match(title, artist, r.get("trackName", ""), r.get("artistName", "")) and r.get("collectionName"):
            return {"title": r["trackName"], "artist": r["artistName"], "album": r["collectionName"], "year": year_of(r.get("releaseDate")),
                    "genre": r.get("primaryGenreName") or "", "track_no": int(r.get("trackNumber") or 0), "duration": (r.get("trackTimeMillis") or 0) / 1000,
                    "cover": (r.get("artworkUrl100") or "").replace("100x100", "600x600"), "source": "iTunes"}
    return None


async def deezer(client, title: str, artist: str) -> dict | None:
    data = await get_json(client, "https://api.deezer.com/search", {"q": f'artist:"{artist}" track:"{title}"', "limit": LIMIT})
    for r in data.get("data", []):
        album = r.get("album") or {}
        if match(title, artist, r.get("title", ""), (r.get("artist") or {}).get("name", "")) and album.get("title"):
            return {"title": r["title"], "artist": r["artist"]["name"], "album": album["title"], "year": 0, "genre": "", "track_no": 0,
                    "duration": float(r.get("duration") or 0), "cover": album.get("cover_xl") or album.get("cover_big") or "", "source": "Deezer"}
    return None


async def musicbrainz(client, title: str, artist: str) -> dict | None:
    data = await get_json(client, "https://musicbrainz.org/ws/2/recording", {"query": f'recording:"{title}" AND artist:"{artist}"', "fmt": "json", "limit": LIMIT})
    for r in data.get("recordings", []):
        credit = " ".join(c.get("name", "") for c in r.get("artist-credit", []) if isinstance(c, dict))
        releases = [x for x in r.get("releases", []) if x.get("title")]
        releases.sort(key=lambda x: ((x.get("release-group") or {}).get("primary-type") != "Album", x.get("date") or "9999"))
        if releases and match(title, artist, r.get("title", ""), credit):
            first = releases[0]
            return {"title": r["title"], "artist": credit.strip(), "album": first["title"], "year": year_of(first.get("date")), "genre": "", "track_no": 0,
                    "duration": (r.get("length") or 0) / 1000, "cover": "", "source": "MusicBrainz"}
    return None


SOURCES = (itunes, deezer, musicbrainz)


def merge(found: list[dict]) -> dict | None:
    if not found:
        return None
    base = dict(found[0])
    for other in found[1:]:
        for key in ("album", "year", "genre", "track_no", "cover", "duration"):
            if not base.get(key) and other.get(key):
                base[key] = other[key]
    return base


async def search(client: httpx.AsyncClient, artist: str, title: str) -> dict | None:
    artist, title = clean_query(artist), clean_query(title)
    if not artist or not title:
        return None
    found: list[dict] = []
    for first, second in ((title, artist), (artist, title)):
        for source in SOURCES:
            result = await source(client, first, second)
            if result:
                found.append(result)
            if found and found[0].get("album") and found[0].get("year") and found[0].get("cover"):
                return merge(found)
        if found:
            break
    return merge(found)


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
