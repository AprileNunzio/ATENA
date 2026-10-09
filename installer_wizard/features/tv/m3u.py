import hashlib
import re
import unicodedata
import urllib.parse

MAX_CHANNELS = 20000
MAX_BYTES = 25 * 1024 * 1024
_ATTR = re.compile(r'([A-Za-z0-9_-]{1,32})="([^"]{0,500})"')
_CTRL = re.compile(r"[\x00-\x1f<>]")


class PlaylistError(ValueError):
    pass


def safe_url(url: str) -> str:
    url = str(url or "").strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or len(url) > 2000 or any(c.isspace() for c in url):
        raise PlaylistError("Indirizzo non valido")
    return url


def clean_text(value: str, limit: int) -> str:
    return _CTRL.sub("", str(value or "")).strip()[:limit]


def channel_id(url: str, name: str) -> str:
    return hashlib.sha256(f"{url}|{name}".encode("utf-8")).hexdigest()[:16]


def parse(text: str) -> list[dict]:
    if len(text.encode("utf-8", errors="ignore")) > MAX_BYTES:
        raise PlaylistError("Playlist troppo grande")
    lines = [ln.strip() for ln in text.replace("\r", "\n").split("\n")]
    if not any(ln.upper().startswith("#EXTM3U") for ln in lines[:5]):
        raise PlaylistError("Non è una playlist M3U (manca #EXTM3U)")
    channels, info, group = [], None, ""
    for line in lines:
        if not line:
            continue
        if line.upper().startswith("#EXTINF"):
            head, _, title = line.partition(",")
            attrs = dict(_ATTR.findall(head))
            info = {"name": clean_text(title or attrs.get("tvg-name", ""), 120), "logo": attrs.get("tvg-logo", ""),
                    "group": clean_text(attrs.get("group-title", ""), 80), "tvg_id": clean_text(attrs.get("tvg-id", ""), 80)}
            continue
        if line.upper().startswith("#EXTGRP:"):
            group = clean_text(line[8:], 80)
            continue
        if line.startswith("#"):
            continue
        try:
            url = safe_url(line)
        except PlaylistError:
            info = None
            continue
        meta = info or {"name": clean_text(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1], 120), "logo": "", "group": "", "tvg_id": ""}
        try:
            logo = safe_url(meta["logo"]) if meta["logo"] else ""
        except PlaylistError:
            logo = ""
        name = meta["name"] or "Canale"
        channels.append({"id": channel_id(url, name), "name": name, "group": meta["group"] or group, "logo": logo,
                         "tvg_id": meta["tvg_id"], "url": url})
        info = None
        if len(channels) >= MAX_CHANNELS:
            break
    if not channels:
        raise PlaylistError("Nessun canale valido nella playlist")
    return channels


def norm(text: str) -> str:
    flat = unicodedata.normalize("NFKD", str(text or "").lower()).encode("ascii", "ignore").decode()
    flat = re.sub(r"\(.*?\)|\[.*?\]", " ", flat)
    flat = re.sub(r"\b(hd|fhd|uhd|4k|sd|hevc|h265|backup)\b", " ", flat)
    return re.sub(r"[^a-z0-9]+", " ", flat).strip()


def find(channels: list[dict], query: str) -> dict | None:
    q = norm(query)
    if not q:
        return None
    words = f" {q} "
    best = None
    for ch in channels:
        name = norm(ch["name"])
        if not name:
            continue
        score = 3 if name == q else 2 if f" {name} " in words else 1 if name.startswith(q) else 0
        digits = re.sub(r"\D", "", name) == re.sub(r"\D", "", q) if re.search(r"\d", q) else True
        if score and digits and (not best or (score, -len(name)) > best[0]):
            best = ((score, -len(name)), ch)
    return best[1] if best else None
