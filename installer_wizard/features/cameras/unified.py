import shutil

from config import env_get
from features.cameras import captures, live, options
from features.cameras.cameras import cameras
from features.vision.webcams import webcams

RECORD_KEYS = ("enabled", "record", "consent", "retention_min")


def registry_of(row: dict) -> dict | None:
    if row["kind"] == "ip":
        return cameras.items.get(row["id"][2:])
    if row["kind"] == "local":
        return next((c for c in cameras.items.values() if c.get("kind") == "webcam" and c.get("url") == row["node"]), None)
    return None


def record_view(cam: dict | None, row: dict) -> dict:
    allowed = row["kind"] in ("ip", "local") and not (row["kind"] == "local" and row["main"])
    base = {"available": allowed, "reason": "" if allowed else "La webcam principale è usata dalla visione e non può registrare"
            if row["kind"] == "local" else "Il sensore infrarosso non registra video"}
    if not cam:
        return {**base, "id": "", "enabled": False, "record": False, "consent": False, "retention_min": 5, "recording": False}
    return {**base, "id": cam["id"], "enabled": bool(cam.get("enabled")), "record": bool(cam.get("record")), "consent": bool(cam.get("consent")),
            "retention_min": cam.get("retention_min", 5), "recording": cameras._recording(cam)}


def row_view(row: dict) -> dict:
    cam = registry_of(row)
    reg_id = cam["id"] if cam else ""
    opts = options.get(row["id"])
    return {"id": row["id"], "name": row["name"], "kind": row["kind"], "main": row["main"], "ir": row["ir"], "node": row["node"],
            "stream": row["stream"], "options": {k: v for k, v in opts.items() if k != "controls"}, "has_controls": bool(opts["controls"]),
            "record": record_view(cam, row), "usage": captures.usage(row["id"], reg_id),
            "client_transform": bool(row["main"] and row["kind"] == "local"), "controllable": row["kind"] in ("local", "infrared") and bool(row["node"])}


def orphans(rows: list[dict]) -> list[dict]:
    linked = {registry_of(r)["id"] for r in rows if registry_of(r)}
    return [{"id": c["id"], "name": c["name"], "url_known": bool(c.get("url"))} for c in cameras.items.values()
            if c["id"] not in linked and c.get("kind") == "webcam"]


def overview() -> dict:
    rows = live.all_rows()
    selected = webcams.state.get("selected") or {}
    return {"sources": [row_view(r) for r in sorted(rows, key=lambda r: (r["hidden"], not r["favorite"], r["order"], r["name"]))],
            "saved_webcams": orphans(rows), "problems": webcams.state.get("problems", []), "selected": selected,
            "tools": {"ffmpeg": bool(shutil.which("ffmpeg")), "v4l2": bool(shutil.which("v4l2-ctl")), "recording": env_get("ATENA_CAMERAS", "0") != "0"}}


def set_record(source_id: str, body: dict) -> dict:
    row = live.find(source_id)
    if row is None:
        raise KeyError(source_id)
    view = record_view(registry_of(row), row)
    if not view["available"]:
        raise ValueError(view["reason"])
    data = {k: body[k] for k in RECORD_KEYS if k in body}
    cam = registry_of(row)
    if cam is None:
        cam = cameras.add({"name": row["name"], "kind": "webcam", "url": row["node"], **data})
    else:
        cam = cameras.update(cam["id"], data)
    return record_view(cam, row)


def remove(source_id: str) -> dict:
    row = live.find(source_id)
    if row is None:
        raise KeyError(source_id)
    cam = registry_of(row)
    removed = captures.purge(source_id, cam["id"] if cam else "")
    if cam:
        cameras.delete(cam["id"])
    options.forget(source_id)
    return removed
