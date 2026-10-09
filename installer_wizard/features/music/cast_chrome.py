import asyncio
import json
import logging
from pathlib import Path

from config import DEMO

log = logging.getLogger("atena.music")
VENV_PY = Path("/opt/atena-music/venv/bin/python")
HELPER = Path(__file__).resolve().parent / "cast_helper.py"
READY_MODULE = "pychromecast"


def available() -> bool:
    return VENV_PY.exists() and not DEMO


async def run(request: dict, timeout: float = 25.0) -> dict:
    if not available():
        raise RuntimeError("Supporto Chromecast non installato")
    proc = await asyncio.create_subprocess_exec("nice", "-n", "5", str(VENV_PY), str(HELPER), json.dumps(request),
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Il Chromecast non risponde")
    try:
        result = json.loads(out.decode("utf-8", errors="replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError("Risposta del Chromecast non valida")
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result


def target(device: dict) -> dict:
    return {"uuid": device["uuid"], "host": device["host"], "port": device["port"], "model": device.get("model"), "name": device.get("name")}


async def discover() -> list[dict]:
    if not available():
        return []
    result = await run({"command": "discover"}, 30.0)
    return [{"id": f"cast:{d['uuid']}", "kind": "cast", "name": str(d.get("name") or "Chromecast")[:60], "model": str(d.get("model") or "")[:40],
             "host": d["host"], "port": d["port"], "uuid": d["uuid"]} for d in result.get("devices", []) if d.get("host") and d.get("uuid")]


async def load(device: dict, url: str, meta: dict, start: float = 0.0) -> None:
    await run({"command": "play", **target(device), "url": url, "mime": meta.get("mime", "audio/mpeg"), "title": meta.get("title", ""),
               "artist": meta.get("artist", ""), "album": meta.get("album", ""), "art": meta.get("art", ""), "start": start,
               "video": bool(meta.get("video"))})


async def status(device: dict) -> dict:
    return await run({"command": "status", **target(device)})


async def control(device: dict, action: str, value: float = 0.0) -> None:
    await run({"command": "control", **target(device), "action": action, "value": value})
