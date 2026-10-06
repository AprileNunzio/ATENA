import asyncio
import logging
import shutil
import subprocess
import time

import numpy as np

from config import env_get
from features.cameras import captures, events, live, options
from features.desktop.desk import desk
from state import store

log = logging.getLogger("atena.cameras")
WIDTH, HEIGHT = 64, 36
PIXEL_DELTA = 25
FRAMES = {}
LAST_ALERT: dict[str, float] = {}


def number(key: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(env_get(key, str(default)))))
    except ValueError:
        return default


def decode(jpeg: bytes) -> np.ndarray | None:
    exe = shutil.which("ffmpeg")
    if not exe or not jpeg:
        return None
    try:
        result = subprocess.run([exe, "-nostdin", "-loglevel", "error", "-f", "image2pipe", "-i", "pipe:0", "-vf",
                                 f"scale={WIDTH}:{HEIGHT},format=gray", "-frames:v", "1", "-f", "rawvideo", "pipe:1"],
                                input=jpeg, capture_output=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if len(result.stdout) != WIDTH * HEIGHT:
        return None
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(HEIGHT, WIDTH).astype(np.int16)


def changed(previous: np.ndarray, current: np.ndarray) -> float:
    return float((np.abs(previous - current) > PIXEL_DELTA).mean())


def threshold(sensitivity: int) -> float:
    return max(0.008, 0.22 - 0.021 * max(1, min(10, sensitivity)))


def moved(previous: np.ndarray | None, current: np.ndarray, sensitivity: int) -> bool:
    return previous is not None and changed(previous, current) >= threshold(sensitivity)


async def alert(row: dict, opts: dict) -> None:
    events.add("motion", row["id"], row["name"], f"Movimento rilevato: {row['name']}")
    store.event("INFO", f"Movimento rilevato: {row['name']}", "cameras")
    desk.show("notice", {"icon": "🏃", "title": "Movimento", "text": f"Movimento rilevato: {row['name']}"}, key=f"motion:{row['id']}", ttl=30)
    if opts["photo_on_motion"]:
        try:
            await captures.take(row)
        except (RuntimeError, ValueError, OSError):
            log.warning("Foto al movimento non salvata: %s", row["name"])


async def check(row: dict, opts: dict, cooldown: int) -> None:
    jpeg = await live.snapshot_bytes(row)
    gray = await asyncio.to_thread(decode, jpeg) if jpeg else None
    if gray is None:
        return
    previous = FRAMES.get(row["id"])
    FRAMES[row["id"]] = gray
    if moved(previous, gray, opts["sensitivity"]) and time.time() - LAST_ALERT.get(row["id"], 0) >= cooldown:
        LAST_ALERT[row["id"]] = time.time()
        await alert(row, opts)


async def tick() -> int:
    saved = options.read()
    cooldown = number("ATENA_CAMERAS_MOTION_COOLDOWN", 60, 10, 3600)
    watched = [r for r in live.all_rows() if (saved.get(r["id"]) or {}).get("motion")]
    for gone in set(FRAMES) - {r["id"] for r in watched}:
        FRAMES.pop(gone, None)
    for row in watched:
        try:
            await check(row, saved[row["id"]], cooldown)
        except Exception:
            log.exception("Controllo del movimento non riuscito: %s", row["name"])
    return len(watched)


async def run() -> None:
    while True:
        await tick()
        await asyncio.sleep(number("ATENA_CAMERAS_MOTION_EVERY", 5, 2, 60))
