import re
from pathlib import Path

from features.music import layout

ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
SLASH = re.compile(r"(?<=\w)/(?=\w)")
UNKNOWN_ARTIST = "Senza artista"
SINGLES = "Singoli"
LEGACY = {"artista sconosciuto", "album sconosciuto"}
UNASSIGNED = {UNKNOWN_ARTIST.lower(), "artista sconosciuto"}
TITLE_MAX = 140


def clean(text: str, fallback: str, limit: int = 90) -> str:
    plain = SLASH.sub("-", str(text or ""))
    cleaned = ILLEGAL.sub(" ", plain).strip(" .")
    return re.sub(r"\s+", " ", cleaned)[:limit].strip(" .") or fallback


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def no_artist(value) -> bool:
    return str(value or "").strip().lower() in UNASSIGNED or not str(value or "").strip()


def no_album(value) -> bool:
    return str(value or "").strip().lower() in LEGACY | {SINGLES.lower()} or not str(value or "").strip()


def known_artist(info: dict) -> str:
    for key in ("artist", "album_artist"):
        if not no_artist(info.get(key)):
            return str(info[key]).strip()
    return ""


def number(info: dict) -> str:
    no, disc = int(info.get("track_no") or 0), int(info.get("disc_no") or 1)
    if not no:
        return ""
    return f"{disc}-{no:02d}" if disc > 1 else f"{no:02d}"


def title_of(info: dict, artist: str) -> str:
    title = str(info.get("title") or "").strip()
    prefix = f"{artist} - "
    return title[len(prefix):].strip() if artist and title.lower().startswith(prefix.lower()) else title


def filename(info: dict, suffix: str) -> str:
    artist = "" if no_artist(info.get("artist")) else str(info["artist"]).strip()
    parts = [number(info), clean(artist, "", 60), clean(title_of(info, artist), "Brano", 90)]
    base = clean(" - ".join(p for p in parts if p), "Brano", TITLE_MAX)
    year = int(info.get("year") or 0)
    return f"{base}{f' ({year})' if 1000 < year < 3000 else ''}{suffix.lower()}"


def reuse(parent: Path, wanted: str) -> Path:
    target = parent / wanted
    if target.exists() or not parent.is_dir():
        return target
    key = squash(wanted)
    for child in parent.iterdir():
        if child.is_dir() and squash(child.name) == key:
            return child
    return target


def directory(info: dict) -> Path | None:
    artist = known_artist({"artist": info.get("album_artist"), "album_artist": info.get("artist")})
    if not artist:
        return None
    album = SINGLES if no_album(info.get("album")) else clean(info["album"], SINGLES)
    return reuse(reuse(layout.library(), clean(artist, "Artista")), album)


def destination(info: dict, suffix: str) -> Path | None:
    folder = directory(info)
    return None if folder is None else folder / filename(info, suffix)


def needs_new_folder(relative: Path, info: dict | None = None) -> bool:
    folders = [p.lower() for p in relative.parts[:-1]]
    if len(folders) < 2 or any(p in LEGACY | UNASSIGNED | {"06 musica", "da smistare", "libreria"} for p in folders):
        return True
    return bool(info) and folders[-1] == SINGLES.lower() and not no_album(info.get("album"))
