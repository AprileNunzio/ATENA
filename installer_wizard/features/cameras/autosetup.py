import asyncio
import json
import logging
import os
import platform
import time

from config import STATE_DIR, env_get
from features.vision import ir_auto, ir_configure, ir_emitter
from features.vision import webcams as cams
from state import store

log = logging.getLogger("atena.cameras")
FILE = STATE_DIR / "cameras" / "ir_auto.json"
INTERVAL = 30
DARK_AFTER = 60
RETRY_AFTER = 7 * 86400


def enabled() -> bool:
    return env_get("ATENA_IR_AUTO", "1").strip() != "0"


def read() -> dict:
    try:
        raw = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, (int, float))} if isinstance(raw, dict) else {}


def remember(device: str, at: float) -> None:
    data = read()
    data[device] = at
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, FILE)


def due(device: str | None, state: str, configured: bool, supported: bool, busy: bool, tried: dict, dark_for: float, now: float) -> bool:
    if not device or not supported or busy or configured or state != "dark" or dark_for < DARK_AFTER:
        return False
    return now - tried.get(device, 0) >= RETRY_AFTER


def supported() -> bool:
    return platform.machine() in ("x86_64", "AMD64")


async def keep_service() -> None:
    if ir_emitter.tool_path() and ir_emitter.configured() and not ir_emitter.service_active():
        try:
            await ir_emitter.enable_service()
            store.event("INFO", "Emettitore infrarosso riattivato a ogni avvio", "cameras")
        except RuntimeError as exc:
            log.warning("Servizio dell'emettitore non attivato: %s", exc)


async def step(dark_since: float | None) -> float | None:
    status = cams.read_json(cams.IR_STATUS_FILE).get("state", "")
    device = (cams.webcams.state.get("selected") or {}).get("ir")
    now = time.time()
    dark_since = (dark_since or now) if status == "dark" else None
    busy = ir_auto.state["running"] or ir_configure.session["running"] or ir_emitter.state["busy"]
    if enabled() and due(device, status, ir_emitter.configured(), supported(), busy, read(), now - (dark_since or now), now):
        remember(device, now)
        store.event("INFO", f"Infrarosso al buio su {device}: avvio la configurazione automatica", "cameras")
        ir_auto.start()
    await keep_service()
    return dark_since


async def run() -> None:
    dark_since = None
    while True:
        await asyncio.sleep(INTERVAL)
        try:
            dark_since = await step(dark_since)
        except Exception:
            log.exception("Controllo automatico dell'infrarosso non riuscito")
