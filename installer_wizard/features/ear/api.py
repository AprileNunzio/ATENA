import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket

from access import require_admin, require_display
from config import env_get
from features.desktop.desk import desk
from features.ear import keycheck, proxy
from state import store

public_routes = APIRouter()
admin_routes = APIRouter()
REVIEW_DIR = Path(os.environ.get("ATENA_EAR_REVIEW_DIR", "/var/lib/atena/ear_review"))
TUNING_FILE = Path(os.environ.get("ATENA_EAR_TUNING", "/var/lib/atena/ear_tuning.json"))


def on(key: str, default: str) -> bool:
    return env_get(key, default).strip().lower() not in ("0", "off", "no", "false")


@public_routes.get("/api/ear/config")
async def ear_config(request: Request):
    require_display(request, "Solo dal display")
    agc = env_get("ATENA_MIC_AGC", "auto").strip().lower()
    return {"echoCancellation": on("ATENA_MIC_EC", "1"), "noiseSuppression": on("ATENA_MIC_NS", "0"),
            "autoGainControl": agc in ("1", "on", "yes", "true"), "autoLevel": agc == "auto"}


@admin_routes.get("/api/ear/review")
async def ear_review(request: Request):
    require_admin(request)
    try:
        data = json.loads((REVIEW_DIR / "summary.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {"state": "nessuna analisi ancora", "recording": on("ATENA_EAR_RECORD", "1"), "pending": 0, "summary": {"chunks": 0}}
    except (OSError, ValueError) as exc:
        data = {"state": f"riepilogo non leggibile: {exc}"}
    return data


@admin_routes.post("/api/ear/review/purge")
async def ear_purge(request: Request):
    require_admin(request)
    removed = 0
    for path in list((REVIEW_DIR / "chunks").glob("c*")) + list((REVIEW_DIR / "chunks").glob("*.tmp")):
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            store.event("WARN", f"Registrazione non eliminata ({path.name}): {exc}", "ear")
    store.event("INFO", f"Registrazioni dell'ascolto eliminate: {removed} file", "ear")
    return {"ok": True, "removed": removed}


@admin_routes.post("/api/ear/tuning/reset")
async def ear_tuning_reset(request: Request):
    require_admin(request)
    TUNING_FILE.unlink(missing_ok=True)
    store.event("INFO", "Regolazioni automatiche dell'ascolto azzerate", "ear")
    return {"ok": True}

@admin_routes.post("/api/ear/stt/check")
async def ear_stt_check(request: Request):
    require_admin(request)
    body = await request.json()
    try:
        return await keycheck.check(str(body.get("provider") or ""), str(body.get("key") or "")[:300],
                                    str(body.get("url") or "")[:300])
    except keycheck.KeyCheckError as exc:
        raise HTTPException(400, str(exc))


desk.register_source("ear_widget", lambda: {"ear": True} if env_get("ATENA_EAR", "1") != "0" else None)


@public_routes.post("/api/ear/client")
async def ear_client(request: Request):
    require_display(request, "Solo dal display")
    body = await request.json()
    error = str(body.get("error") or "")[:160]
    previous = getattr(store, "mic", None) or {}
    store.mic = {"ok": bool(body.get("ok")), "error": error, "inputs": int(body.get("inputs") or 0),
                 "label": str(body.get("label") or "")[:80], "at": time.time()}
    if error and error != previous.get("error"):
        store.event("WARN", f"Microfono del display: {error}", "ear")
    elif body.get("ok") and previous.get("error"):
        store.event("INFO", f"Microfono del display di nuovo attivo: {store.mic['label'] or 'predefinito'}", "ear")
    return {"ok": True}


@public_routes.websocket("/ws/ear")
async def ear_socket(socket: WebSocket):
    await proxy.proxy(socket)
