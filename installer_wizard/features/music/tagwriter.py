import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from features.music import id3

log = logging.getLogger("atena.music")
FFMPEG_KEYS = {"title": "title", "artist": "artist", "album": "album", "album_artist": "album_artist", "genre": "genre",
               "year": "date", "track_no": "track"}
TIMEOUT = 120


def clean(fields: dict) -> dict:
    return {k: str(v).strip() for k, v in fields.items() if k in FFMPEG_KEYS and v not in (None, "", 0) and str(v).strip()}


def write_ffmpeg(path: Path, values: dict) -> bool:
    binary = shutil.which("ffmpeg")
    if binary is None:
        return False
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".tag-", suffix=path.suffix)
    os.close(handle)
    argv = [binary, "-nostdin", "-loglevel", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy", "-map_metadata", "0"]
    if path.suffix.lower() == ".mp3":
        argv += ["-id3v2_version", "3"]
    for key, value in values.items():
        argv += ["-metadata", f"{FFMPEG_KEYS[key]}={value}"]
    try:
        subprocess.run(argv + [temp], check=True, capture_output=True, timeout=TIMEOUT)
        os.replace(temp, path)
    except (OSError, subprocess.SubprocessError):
        Path(temp).unlink(missing_ok=True)
        raise
    return True


def write(path: Path, fields: dict) -> bool:
    values = clean(fields)
    if not values:
        return False
    try:
        before = path.stat()
        saved = id3.write_wav(path, values) if path.suffix.lower() == ".wav" else write_ffmpeg(path, values)
        if saved:
            os.utime(path, (before.st_atime, before.st_mtime))
        return saved
    except Exception as exc:
        log.warning("Dati non scritti nel file %s: %s", path.name, exc)
        return False
