import json
import os
import re

from config import STATE_DIR

FILE = STATE_DIR / "cameras" / "options.json"
SOURCE_RE = re.compile(r"^[wci]-[0-9a-f]{8}$")
ROTATIONS = (0, 90, 180, 270)
FILTERS = {90: ["transpose=1"], 180: ["hflip", "vflip"], 270: ["transpose=2"]}
WIDTHS = (0, 320, 480, 640, 960, 1280, 1920)
MAX_CONTROLS = 24
DEFAULTS = {"alias": "", "room": "", "rotate": 0, "mirror": False, "fps": 0, "width": 0, "motion": False, "sensitivity": 5, "photo_on_motion": False,
            "hidden": False, "favorite": False, "order": 0, "controls": {}}


def text(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def whole(value, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def controls_of(value, base: dict) -> dict:
    if not isinstance(value, dict):
        return dict(base)
    clean = {}
    for key, number in value.items():
        if re.fullmatch(r"[a-z0-9_]{2,48}", str(key)) and isinstance(number, int) and not isinstance(number, bool):
            clean[str(key)] = max(-1_000_000, min(1_000_000, number))
    return dict(list(clean.items())[:MAX_CONTROLS])


def validate(body: dict, base: dict | None = None) -> dict:
    base = {**DEFAULTS, **(base or {})}
    rotate = whole(body.get("rotate", base["rotate"]), 0, 270, 0)
    width = whole(body.get("width", base["width"]), 0, 1920, 0)
    fps = whole(body.get("fps", base["fps"]), 0, 25, 0)
    return {"alias": text(body.get("alias", base["alias"]), 40), "room": text(body.get("room", base["room"]), 40),
            "rotate": rotate if rotate in ROTATIONS else 0, "mirror": bool(body.get("mirror", base["mirror"])),
            "fps": fps if fps == 0 or fps >= 2 else 2, "width": width if width in WIDTHS else 0,
            "motion": bool(body.get("motion", base["motion"])), "sensitivity": whole(body.get("sensitivity", base["sensitivity"]), 1, 10, 5),
            "photo_on_motion": bool(body.get("photo_on_motion", base["photo_on_motion"])),
            "hidden": bool(body.get("hidden", base["hidden"])), "favorite": bool(body.get("favorite", base["favorite"])),
            "order": whole(body.get("order", base["order"]), 0, 999, 0), "controls": controls_of(body.get("controls"), base["controls"])}


def read() -> dict:
    try:
        raw = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: validate(v, {}) for k, v in raw.items() if SOURCE_RE.match(k) and isinstance(v, dict)} if isinstance(raw, dict) else {}


def write(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FILE)


def get(source_id: str) -> dict:
    return read().get(source_id) or dict(DEFAULTS)


def put(source_id: str, body: dict) -> dict:
    if not SOURCE_RE.match(source_id):
        raise ValueError("Sorgente non valida")
    data = read()
    data[source_id] = validate(body, data.get(source_id))
    write(data)
    return data[source_id]


def forget(source_id: str) -> None:
    data = read()
    if data.pop(source_id, None) is not None:
        write(data)


def filters(opts: dict) -> list[str]:
    return [*FILTERS.get(opts.get("rotate", 0), []), *(["hflip"] if opts.get("mirror") else [])]
