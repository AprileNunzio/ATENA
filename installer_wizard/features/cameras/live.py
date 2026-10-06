import asyncio
import hashlib
import logging
import re
import shutil
import subprocess
import time
import unicodedata

from fastapi.responses import Response, StreamingResponse

from config import env_get
from features.cameras import options
from features.cameras.cameras import cameras
from features.vision.proxy import frame, ir_frame, vision_stream
from features.vision.webcams import webcams

log = logging.getLogger("atena.cameras")
CHUNK = 64 * 1024
MAX_SECONDS = 1800
SNAPSHOT_TIMEOUT = 10
STOP_WORDS = {"il", "lo", "la", "le", "i", "gli", "di", "del", "della", "dello", "dei", "delle", "sul", "sulla", "su", "in", "nel", "nella", "a", "al",
              "alla", "un", "una", "mia", "mio", "per", "favore", "webcam", "web", "cam", "telecamera", "videocamera", "camera", "telecamere",
              "schermo", "tutto", "pieno", "intero", "widget", "live", "diretta", "vedere", "vedi", "apri", "aprimi", "mostra", "mostrami", "fammi",
              "fai", "visualizza", "accendi", "attiva", "avvia", "metti", "guarda", "vediamo", "chiudi", "spegni", "disattiva", "nascondi", "togli",
              "ferma", "elimina", "tutte", "tutti", "ogni", "ingrandisci", "massimizza", "riduci", "esci", "torna", "normale", "quale", "vuoi", "cam"}
ORDINALS = {"prima": 1, "primo": 1, "uno": 1, "seconda": 2, "secondo": 2, "due": 2, "terza": 3, "terzo": 3, "tre": 3, "quarta": 4, "quarto": 4, "quattro": 4,
            "1": 1, "2": 2, "3": 3, "4": 4}
_active = {"count": 0}


def number(key: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(env_get(key, str(default)))))
    except ValueError:
        return default


def plain(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text or "").lower()).encode("ascii", "ignore").decode()


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", plain(text)) if w not in STOP_WORDS]


def local_id(device: dict) -> str:
    return "w-" + hashlib.sha1(device["id"].encode("utf-8")).hexdigest()[:8]


def ir_id(device: dict) -> str:
    return "i-" + hashlib.sha1(device["id"].encode("utf-8")).hexdigest()[:8]


def decorate(row: dict, saved: dict) -> dict:
    opts = saved.get(row["id"]) or options.DEFAULTS
    row.update(alias=opts["alias"] or "", room=opts["room"], rotate=opts["rotate"], mirror=opts["mirror"], hidden=opts["hidden"],
               favorite=opts["favorite"], order=opts["order"], motion=opts["motion"])
    if opts["alias"]:
        row["name"] = opts["alias"]
    return row


def all_rows() -> list[dict]:
    rows = []
    state = webcams.state
    main = (state.get("selected") or {}).get("rgb")
    main_ir = (state.get("selected") or {}).get("ir")
    for device in state.get("devices", []):
        if device.get("rgb"):
            rows.append({"id": local_id(device), "name": device["name"], "kind": "local", "device": device["rgb"], "node": device["rgb"],
                         "main": device["rgb"] == main, "ir": bool(device.get("has_ir")), "stream": True})
        if device.get("ir"):
            rows.append({"id": ir_id(device), "name": f"{device['name']} (infrarossi)", "kind": "infrared", "device": device["ir"],
                         "node": device["ir"], "main": device["ir"] == main_ir, "ir": True, "stream": False})
    for cam in sorted(cameras.items.values(), key=lambda c: c.get("created", 0)):
        if cam.get("kind") != "webcam" and cam.get("url"):
            rows.append({"id": f"c-{cam['id']}", "name": cam["name"], "kind": "ip", "device": cam["url"], "node": "", "main": False,
                         "ir": False, "stream": True})
    seen: dict[str, int] = {}
    for row in rows:
        seen[row["name"]] = seen.get(row["name"], 0) + 1
        if seen[row["name"]] > 1:
            row["name"] = f"{row['name']} {seen[row['name']]}"
    saved = options.read()
    return [decorate(row, saved) for row in rows]


def listing() -> list[dict]:
    return [r for r in all_rows() if r["kind"] != "infrared" and not r["hidden"]]


def public(rows: list[dict]) -> list[dict]:
    return [{"id": r["id"], "name": r["name"], "kind": r["kind"], "main": r["main"], "ir": r["ir"], "rotate": r["rotate"], "mirror": r["mirror"],
             "client_transform": bool(r["main"] and r["kind"] == "local"), "room": r["room"], "stream": r["stream"]} for r in rows]


def find(source_id: str) -> dict | None:
    return next((r for r in all_rows() if r["id"] == source_id), None)


def match(text: str, rows: list[dict] | None = None) -> list[dict]:
    rows = listing() if rows is None else rows
    wanted = words(text)
    if not wanted:
        return []
    scored = []
    for index, row in enumerate(rows, 1):
        tokens = set(words(row["name"]))
        score = sum(2 for w in wanted if w in tokens) + sum(1 for w in wanted if len(w) >= 3 and any(w in t or t in w for t in tokens if len(t) >= 3))
        score += sum(3 for w in wanted if ORDINALS.get(w) == index)
        if row["ir"] and any(w in ("infrarossi", "infrarosso", "ir", "nir") for w in wanted):
            score += 3
        if row["kind"] == "ip" and any(w in ("ip", "rete", "esterna", "ingresso") for w in wanted):
            score += 1
        if score:
            scored.append((score, row))
    if not scored:
        return []
    top = max(s for s, _ in scored)
    return [r for s, r in scored if s == top]


def ffmpeg_input(source: dict) -> list[str]:
    target = source["device"]
    if source["kind"] == "ip" and target.lower().startswith(("rtsp://", "rtsps://")):
        return ["-rtsp_transport", "tcp", "-i", target]
    if source["kind"] == "ip":
        return ["-i", target]
    path = target if target.startswith("/dev/") else f"/dev/video{target}"
    return ["-f", "v4l2", "-i", path]


def ffmpeg_command(source: dict, fps: int, width: int, single: bool = False) -> list[str]:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg non è installato")
    opts = options.get(source.get("id", ""))
    chain = [*options.filters(opts), f"fps={opts['fps'] or fps}", f"scale={opts['width'] or width}:-2"]
    args = [exe, "-nostdin", "-loglevel", "error", *ffmpeg_input(source), "-vf", ",".join(chain), "-q:v", "6"]
    if single:
        return args + ["-frames:v", "1", "-f", "image2", "-c:v", "mjpeg", "pipe:1"]
    return args + ["-f", "mpjpeg", "-boundary_tag", "frame", "pipe:1"]


def settings() -> tuple[int, int, int]:
    return number("ATENA_LIVECAM_FPS", 8, 2, 25), number("ATENA_LIVECAM_WIDTH", 640, 320, 1920), number("ATENA_LIVECAM_MAX", 2, 1, 6)


async def stream(source: dict):
    if not source.get("stream", True):
        raise RuntimeError("Questa sorgente offre solo immagini singole")
    if source["main"] and source["kind"] == "local":
        return await vision_stream("/live.mjpg")
    fps, width, limit = settings()
    if _active["count"] >= limit:
        raise RuntimeError("Troppe telecamere in diretta: chiudine una")
    command = ffmpeg_command(source, fps, width)
    proc = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    _active["count"] += 1
    started = time.time()

    async def relay():
        try:
            while time.time() - started < MAX_SECONDS:
                data = await proc.stdout.read(CHUNK)
                if not data:
                    break
                yield data
        finally:
            _active["count"] = max(0, _active["count"] - 1)
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

    return StreamingResponse(relay(), media_type="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control": "no-store"})


async def snapshot_bytes(source: dict) -> bytes | None:
    if source["kind"] == "infrared":
        return await ir_frame()
    if source["main"] and source["kind"] == "local":
        return await frame()
    fps, width, _ = settings()
    try:
        command = ffmpeg_command(source, fps, width, True)
    except RuntimeError:
        return None
    result = await asyncio.to_thread(run_once, command)
    return result or None


def run_once(command: list[str]) -> bytes:
    try:
        return subprocess.run(command, capture_output=True, timeout=SNAPSHOT_TIMEOUT, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return b""


async def snapshot(source: dict) -> Response | None:
    data = await snapshot_bytes(source)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"}) if data else None
