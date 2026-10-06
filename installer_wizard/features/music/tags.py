import logging
import re
from pathlib import Path

from features.music import naming

try:
    from tinytag import TinyTag
except ImportError:
    TinyTag = None

log = logging.getLogger("atena.music")
DASH = re.compile(r"^\s*(.+?)\s+[-–—]\s+(.+)$")
LEADING_NO = re.compile(r"^\s*(\d{1,3})\s*[-._)]\s*(.+)$")
YEAR = re.compile(r"(\d{4})")
ANCHORS = ("libreria", "da smistare")
STRUCTURE = {"libreria", "da smistare", "playlist", "copertine", "cestino", "06 musica", "condivisa", "_duplicati", "musica", "atena", "srv"}
EMPTY = {"title": "", "artist": "", "album_artist": "", "album": "", "track_no": 0, "disc_no": 1, "year": 0, "genre": "",
         "duration": 0.0, "bitrate": 0, "cover": False}
def number(text: str) -> int:
    match = re.match(r"\d+", str(text or "").strip())
    return int(match.group()) if match else 0


def from_path(path: Path) -> dict:
    stem = path.stem.replace("_", " ")
    parts = path.parts
    lowered = [p.lower() for p in parts]
    anchor = max((i for i, p in enumerate(lowered[:-1]) if p in ANCHORS), default=None)
    folders = list(parts[anchor + 1:-1]) if anchor is not None else list(parts[-3:-1])
    folders = [p for p in folders if p.lower() not in STRUCTURE][-2:]
    out = {"title": stem, "artist": "", "track_no": 0}
    lead = LEADING_NO.match(stem)
    rest = lead.group(2) if lead else stem
    if lead:
        out["track_no"] = int(lead.group(1))
    match = DASH.match(rest)
    if match:
        out.update(artist=match.group(1).strip(), title=match.group(2).strip())
    else:
        out["title"] = rest.strip()
    if not out["artist"] and len(folders) == 2:
        out["artist"] = folders[0]
    if len(folders) >= 1:
        out["album"] = folders[-1]
    return out


def _load(path: Path, image: bool = False):
    if TinyTag is None:
        return None
    try:
        return TinyTag.get(str(path), image=image)
    except Exception as exc:
        log.debug("Tag non leggibili in %s: %s", path.name, exc)
        return None


def read(path: Path) -> dict:
    info = dict(EMPTY)
    guess = from_path(path)
    tag = _load(path, image=True)
    if tag is not None:
        for key, attr in (("title", "title"), ("artist", "artist"), ("album_artist", "albumartist"), ("album", "album"),
                          ("genre", "genre")):
            info[key] = str(getattr(tag, attr, None) or "").strip()
        found = YEAR.search(str(tag.year or ""))
        info["year"] = int(found.group(1)) if found else 0
        info["track_no"] = int(tag.track or 0)
        info["disc_no"] = int(tag.disc or 0) or 1
        info["duration"] = round(float(tag.duration or 0), 2)
        info["bitrate"] = int(tag.bitrate or 0)
        info["cover"] = tag.images.any is not None
    for key in ("title", "artist", "album", "track_no"):
        if not info[key]:
            info[key] = guess.get(key, info[key])
    info["title"] = info["title"] or path.stem
    info["artist"] = info["artist"] or info["album_artist"] or naming.UNKNOWN_ARTIST
    info["album"] = info["album"] or naming.SINGLES
    info["album_artist"] = info["album_artist"] or info["artist"]
    return info


def embedded_cover(path: Path) -> bytes | None:
    tag = _load(path, image=True)
    image = tag.images.any if tag is not None else None
    return bytes(image.data) if image is not None and image.data else None
