import asyncio
import re
import shutil
import subprocess
import time
from pathlib import Path

from config import env_get
from features.cameras import options
from features.cameras.cameras import CAM_DIR

PHOTOS = CAM_DIR / "photos"
PHOTO_RE = re.compile(r"^photo_\d{8}_\d{6}(?:_\d)?\.jpg$")
CLIP_RE = re.compile(r"^seg_\d{8}_\d{6}\.mp4$")
SOURCE_RE = options.SOURCE_RE
REGISTRY_RE = re.compile(r"^[0-9a-f]{8}$")


def limit() -> int:
    try:
        return max(10, min(1000, int(env_get("ATENA_CAMERAS_PHOTOS_MAX", "200"))))
    except ValueError:
        return 200


def folder(source_id: str) -> Path:
    if not SOURCE_RE.match(source_id):
        raise ValueError("Sorgente non valida")
    return PHOTOS / source_id


def transform(data: bytes, opts: dict) -> bytes:
    chain = options.filters(opts)
    exe = shutil.which("ffmpeg")
    if not chain or not exe:
        return data
    try:
        result = subprocess.run([exe, "-nostdin", "-loglevel", "error", "-f", "image2pipe", "-i", "pipe:0", "-vf", ",".join(chain),
                                 "-frames:v", "1", "-f", "image2", "-c:v", "mjpeg", "-q:v", "3", "pipe:1"],
                                input=data, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return data
    return result.stdout or data


def prune(path: Path) -> None:
    files = sorted(path.glob("photo_*.jpg"))
    for old in files[:-limit()]:
        old.unlink(missing_ok=True)


def save(source_id: str, data: bytes) -> dict:
    path = folder(source_id)
    path.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    name, n = f"photo_{stamp}.jpg", 0
    while (path / name).exists() and n < 9:
        n += 1
        name = f"photo_{stamp}_{n}.jpg"
    (path / name).write_bytes(data)
    prune(path)
    return {"name": name, "size": len(data)}


async def take(source: dict) -> dict:
    from features.cameras import live
    data = await live.snapshot_bytes(source)
    if not data:
        raise RuntimeError("Nessun fotogramma dalla telecamera")
    data = await asyncio.to_thread(transform, data, options.get(source["id"]))
    return await asyncio.to_thread(save, source["id"], data)


def photos(source_id: str) -> list[dict]:
    path = folder(source_id)
    rows = [{"name": p.name, "size": p.stat().st_size, "at": p.stat().st_mtime} for p in path.glob("photo_*.jpg") if PHOTO_RE.match(p.name)]
    return sorted(rows, key=lambda r: r["name"], reverse=True)


def photo_path(source_id: str, name: str) -> Path:
    path = folder(source_id) / name
    if not PHOTO_RE.match(name) or not path.is_file():
        raise FileNotFoundError(name)
    return path


def delete_photo(source_id: str, name: str) -> None:
    photo_path(source_id, name).unlink()


def clips_folder(registry_id: str) -> Path:
    if not REGISTRY_RE.match(registry_id):
        raise ValueError("Telecamera non valida")
    return CAM_DIR / registry_id


def clips(registry_id: str) -> list[dict]:
    rows = [{"name": p.name, "size": p.stat().st_size, "at": p.stat().st_mtime} for p in clips_folder(registry_id).glob("seg_*.mp4") if CLIP_RE.match(p.name)]
    return sorted(rows, key=lambda r: r["name"], reverse=True)


def clip_path(registry_id: str, name: str) -> Path:
    path = clips_folder(registry_id) / name
    if not CLIP_RE.match(name) or not path.is_file():
        raise FileNotFoundError(name)
    return path


def purge(source_id: str, registry_id: str = "") -> dict:
    removed = {"photos": 0, "clips": 0}
    for p in folder(source_id).glob("photo_*.jpg"):
        p.unlink(missing_ok=True)
        removed["photos"] += 1
    if registry_id:
        for p in clips_folder(registry_id).glob("seg_*.mp4"):
            p.unlink(missing_ok=True)
            removed["clips"] += 1
    return removed


def usage(source_id: str, registry_id: str = "") -> dict:
    photo_bytes = sum(r["size"] for r in photos(source_id)) if folder(source_id).exists() else 0
    clip_rows = clips(registry_id) if registry_id and clips_folder(registry_id).exists() else []
    return {"photos": len(photos(source_id)) if folder(source_id).exists() else 0, "photo_bytes": photo_bytes,
            "clips": len(clip_rows), "clip_bytes": sum(r["size"] for r in clip_rows)}
