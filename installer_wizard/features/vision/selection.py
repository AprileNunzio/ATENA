import json
import os
from pathlib import Path

STATE = Path(os.environ.get("ATENA_WEBCAMS_FILE", "/var/lib/atena/webcams.json"))
FALLBACK = os.environ.get("ATENA_CAMERA", "/dev/video0")
SIZES = {"640x480": (640, 480), "1280x720": (1280, 720), "1920x1080": (1920, 1080)}


def current() -> dict:
    try:
        raw = json.loads(STATE.read_text(encoding="utf-8")).get("selected") or {}
        stamp = STATE.stat().st_mtime
    except (OSError, ValueError, AttributeError):
        raw, stamp = {}, 0.0
    return {"rgb": raw.get("rgb") or FALLBACK, "ir": raw.get("ir"), "rgb_mode": raw.get("rgb_mode"),
            "ir_mode": raw.get("ir_mode"), "stamp": stamp}


def capture_size(mode: dict | None, cores: int) -> tuple[int, int]:
    wanted = os.environ.get("ATENA_CAMERA_RES", "auto").strip()
    width, height = SIZES.get(wanted) or ((1280, 720) if cores >= 4 else (640, 480))
    if mode and mode.get("width") and mode.get("height"):
        width, height = min(width, mode["width"]), min(height, mode["height"])
    return width, height


def ir_enabled() -> bool:
    return os.environ.get("ATENA_IR_MODE", "auto").strip().lower() != "off"


def liveness_mode() -> str:
    value = os.environ.get("ATENA_LIVENESS", "advisory").strip().lower()
    return value if value in ("off", "advisory", "strict") else "advisory"


def liveness_minimum() -> float:
    try:
        return max(0.1, min(0.95, float(os.environ.get("ATENA_LIVENESS_MIN", "0.55"))))
    except ValueError:
        return 0.55
