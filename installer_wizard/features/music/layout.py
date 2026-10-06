from pathlib import Path

from config import STATE_DIR
from features.shares import archive

AUDIO = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wma", ".aiff", ".aif", ".alac", ".ape", ".mka"}
BROWSER_SAFE = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav"}
MIME = {".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg",
        ".oga": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav", ".wma": "audio/x-ms-wma", ".aiff": "audio/aiff",
        ".aif": "audio/aiff", ".alac": "audio/mp4", ".ape": "audio/x-ape", ".mka": "audio/x-matroska"}
LIBRARY = "Libreria"
INBOX = "Da smistare"
PLAYLISTS = "Playlist"
COVERS = "Copertine"
TRASH = "Cestino"
OLD_TRASH = ".cestino"
DB_FILE = STATE_DIR / "music.db"


def root() -> Path:
    base = archive.folder("musica")
    for sub in archive.SUBFOLDERS["musica"]:
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def library() -> Path:
    return root() / LIBRARY


def inbox() -> Path:
    return root() / INBOX


def playlists() -> Path:
    return root() / PLAYLISTS


def covers() -> Path:
    return root() / COVERS


def trash() -> Path:
    return root() / TRASH


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO and not path.name.startswith(".")


def mime(path: str) -> str:
    return MIME.get(Path(path).suffix.lower(), "application/octet-stream")


def inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True
