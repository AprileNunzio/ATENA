import hmac
import ipaddress
import json
import os
import re
import secrets
import time
from pathlib import Path

import psutil
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from access import NO_CACHE, is_local, require_admin
from config import DEMO, ETC_DIR, STATE_DIR, read_env
from state import store

SETUP_FILE = STATE_DIR / "setup.json"
ANSWERS_FILE = ETC_DIR / "answers.env"
WAKE_DIR = Path(os.environ.get("ATENA_WAKEWORD_MODELS", str(STATE_DIR / "wakeword" if DEMO else "/opt/atena-ear/wakeword")))
WAKE_MAX_BYTES = 20 * 1024 * 1024
MAX_ATTEMPTS = 5
LOCKOUT_S = 600

PROFILES = {
    "auto": {"label": "Automatico", "model": "", "size_gb": 0.0,
             "note": "Atena sceglie da sola in base all'hardware."},
    "leggero": {"label": "Leggero", "model": "granite3.3:2b", "size_gb": 1.9, "min_ram_gb": 6,
                "note": "Per mini PC e computer con poca memoria."},
    "bilanciato": {"label": "Bilanciato", "model": "granite3.3:8b", "size_gb": 4.9, "min_ram_gb": 14,
                   "note": "Ragionamento migliore, serve un computer recente."},
    "potente": {"label": "Potente", "model": "qwen2.5:14b", "size_gb": 9.0, "min_ram_gb": 28,
                "note": "Massima qualità, consigliato con scheda video da 12 GB o più."},
}
VOICE_CHOICES = {
    "if_sara": "Sara — femminile, naturale",
    "it_IT-serena-high": "Serena — femminile, alta qualità",
    "it_IT-paola-medium": "Paola — femminile, veloce",
    "im_nicola": "Nicola — maschile, naturale",
}
LANGS = {"it": "Italiano", "en": "English"}

NAME_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ-]{0,39}")
HA_URL_RE = re.compile(r"https?://[A-Za-z0-9.-]{1,253}(:\d{1,5})?(/[A-Za-z0-9._~/-]{0,200})?")
HA_TOKEN_RE = re.compile(r"[A-Za-z0-9._-]{20,512}")
TELEGRAM_RE = re.compile(r"\d{5,12}:[A-Za-z0-9_-]{30,64}")
ANSWER_KEYS = {"ATENA_USER_NAME", "ATENA_UI_LANG", "ATENA_VOICE", "ATENA_LLM_MODEL", "ATENA_COMMERCIAL",
               "HOME_ASSISTANT_URL", "HOME_ASSISTANT_TOKEN", "ATENA_TELEGRAM_TOKEN", "ATENA_SMB_PASSWORD"}
SMB_RE = re.compile(r"[A-Za-z0-9_.@%+=:,-]{12,128}")

public_routes = APIRouter()
admin_routes = APIRouter()
PREVIEW_TEXT = "Ciao, sono Atena. Questa è la mia voce: ti piace?"
PREVIEW_GAP_S = 2.0
_preview = {"at": 0.0, "lock": None}


class Guard:
    def __init__(self) -> None:
        self.code = f"{secrets.randbelow(10 ** 6):06d}"
        self.failures = 0
        self.locked_until = 0.0

    def check(self, given: str) -> None:
        if time.time() < self.locked_until:
            raise HTTPException(429, "Troppi tentativi: riprova tra qualche minuto")
        if hmac.compare_digest(str(given or "").strip(), self.code):
            self.failures = 0
            return
        self.failures += 1
        if self.failures >= MAX_ATTEMPTS:
            self.failures = 0
            self.locked_until = time.time() + LOCKOUT_S
        raise HTTPException(403, "Codice di configurazione non valido")


guard = Guard()


def done() -> bool:
    try:
        return bool(json.loads(SETUP_FILE.read_text(encoding="utf-8")).get("done"))
    except (OSError, ValueError):
        return False


def _mark_done(source: str) -> None:
    SETUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETUP_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"done": True, "at": time.time(), "source": source}), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, SETUP_FILE)
    store.event("INFO", f"Prima configurazione completata ({source})", "setup")
    store.touch()


def _private_client(request: Request) -> bool:
    if is_local(request):
        return True
    try:
        ip = ipaddress.ip_address(request.client.host if request.client else "")
    except ValueError:
        return False
    return ip.is_private or ip.is_link_local


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    host = request.headers.get("host", "")
    return origin.split("://", 1)[-1].rstrip("/") == host


def require_setup(request: Request) -> None:
    if done():
        raise HTTPException(410, "La prima configurazione è già stata completata: usa il pannello di amministrazione")
    if not _private_client(request):
        raise HTTPException(403, "La prima configurazione è disponibile solo dalla rete di casa")
    if request.method == "POST" and (request.headers.get("X-Atena-Request") != "1" or not _same_origin(request)):
        raise HTTPException(403, "Richiesta non valida")
    if request.method == "POST" and not is_local(request):
        guard.check(request.headers.get("X-Atena-Setup-Code", ""))


def hardware() -> dict:
    mem = psutil.virtual_memory().total / 2 ** 30
    try:
        disk = psutil.disk_usage("/").free / 2 ** 30
    except OSError:
        disk = 0.0
    gpu = read_env().get("ATENA_HW_PROFILE", "") == "gpu"
    if gpu and mem >= 28:
        best = "potente"
    elif mem >= 14:
        best = "bilanciato"
    else:
        best = "leggero"
    return {"ram_gb": round(mem, 1), "disk_free_gb": round(disk, 1), "cpu": psutil.cpu_count() or 0,
            "gpu": gpu, "recommended": best}


def _clean(raw: dict) -> dict:
    out: dict[str, str] = {}
    name = str(raw.get("name") or "").strip()
    if name:
        if not NAME_RE.fullmatch(name):
            raise HTTPException(400, "Il nome può contenere solo lettere e trattini, senza spazi")
        out["ATENA_USER_NAME"] = name
    lang = str(raw.get("lang") or "it")
    if lang not in LANGS:
        raise HTTPException(400, "Lingua non supportata")
    out["ATENA_UI_LANG"] = lang
    profile = str(raw.get("profile") or "auto")
    if profile not in PROFILES:
        raise HTTPException(400, "Profilo non valido")
    if PROFILES[profile]["model"]:
        out["ATENA_LLM_MODEL"] = PROFILES[profile]["model"]
    voice = str(raw.get("voice") or "if_sara")
    if voice not in VOICE_CHOICES:
        raise HTTPException(400, "Voce non disponibile")
    out["ATENA_VOICE"] = voice
    ha_url, ha_token = str(raw.get("ha_url") or "").strip(), str(raw.get("ha_token") or "").strip()
    if ha_url or ha_token:
        if not (HA_URL_RE.fullmatch(ha_url) and HA_TOKEN_RE.fullmatch(ha_token)):
            raise HTTPException(400, "Indirizzo o token di Home Assistant non validi")
        out.update(HOME_ASSISTANT_URL=ha_url.rstrip("/"), HOME_ASSISTANT_TOKEN=ha_token, ATENA_HOME_ASSISTANT="1")
    telegram = str(raw.get("telegram") or "").strip()
    if telegram:
        if not TELEGRAM_RE.fullmatch(telegram):
            raise HTTPException(400, "Token di Telegram non valido")
        out.update(ATENA_TELEGRAM_TOKEN=telegram, ATENA_TELEGRAM="1")
    out["ATENA_COMMERCIAL"] = "1" if raw.get("commercial") is True else "0"
    return out


async def _apply(updates: dict, source: str) -> None:
    from settings import apply_config
    await apply_config(updates, f"prima configurazione ({source})")


@public_routes.get("/setup")
async def setup_page(request: Request):
    if done() or not _private_client(request):
        return RedirectResponse("/", status_code=303)
    from pages import page
    return page("setup/setup.html")


@public_routes.post("/api/setup/verify")
async def setup_verify(_: None = Depends(require_setup)):
    return JSONResponse({"ok": True}, headers=NO_CACHE)


@public_routes.post("/api/setup/voice")
async def setup_voice_preview(voice: str, request: Request, _: None = Depends(require_setup)):
    import asyncio
    if voice not in VOICE_CHOICES:
        raise HTTPException(400, "Voce non disponibile")
    if _preview["lock"] is None:
        _preview["lock"] = asyncio.Lock()
    if _preview["lock"].locked() or time.time() - _preview["at"] < PREVIEW_GAP_S:
        raise HTTPException(429, "Un momento: sto ancora parlando")
    async with _preview["lock"]:
        _preview["at"] = time.time()
        if DEMO:
            raise HTTPException(409, "Voce non ancora installata: la potrai ascoltare tra poco")
        from features.voices import catalog, synthesis
        if catalog.is_piper(voice) and not catalog.piper_installed(voice):
            raise HTTPException(409, "Voce non ancora installata: la potrai ascoltare tra poco")
        try:
            wav = await asyncio.wait_for(synthesis.speak_with(PREVIEW_TEXT, voice, 1.0), timeout=30)
        except Exception:
            raise HTTPException(409, "Voce non ancora installata: la potrai ascoltare tra poco")
    return Response(wav, media_type="audio/wav", headers=NO_CACHE)


@public_routes.get("/api/setup")
async def setup_state(request: Request):
    if done():
        return JSONResponse({"needed": False}, headers=NO_CACHE)
    if not _private_client(request):
        raise HTTPException(403, "La prima configurazione è disponibile solo dalla rete di casa")
    env = read_env()
    return JSONResponse({
        "needed": True, "local": is_local(request), "code": guard.code if is_local(request) else None,
        "hardware": hardware(), "languages": LANGS, "voices": VOICE_CHOICES,
        "profiles": {k: {kk: vv for kk, vv in v.items() if kk != "min_ram_gb"} for k, v in PROFILES.items()},
        "current": {"name": env.get("ATENA_USER_NAME", ""), "lang": env.get("ATENA_UI_LANG", "it")},
        "wakeword": (WAKE_DIR / "ehi_atena.onnx").exists(),
    }, headers=NO_CACHE)


@public_routes.post("/api/setup")
async def setup_save(request: Request, _: None = Depends(require_setup)):
    try:
        raw = await request.json()
    except ValueError:
        raise HTTPException(400, "Dati non validi")
    if not isinstance(raw, dict):
        raise HTTPException(400, "Dati non validi")
    updates = _clean(raw)
    password = ""
    if raw.get("shares", True):
        password = secrets.token_urlsafe(18)
        updates["ATENA_SMB_PASSWORD"] = password
    await _apply(updates, "procedura guidata")
    _mark_done("procedura guidata")
    return JSONResponse({"ok": True, "shares_password": password}, headers=NO_CACHE)


@public_routes.post("/api/setup/wakeword")
async def setup_wakeword(request: Request, _: None = Depends(require_setup)):
    return await _store_wakeword(request)


@admin_routes.post("/api/setup/wakeword")
async def admin_wakeword(request: Request, _: str = Depends(require_admin)):
    return await _store_wakeword(request)


async def _read_capped(request: Request) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > WAKE_MAX_BYTES:
        raise HTTPException(413, "Il modello deve essere un file .onnx tra 1 KB e 20 MB")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > WAKE_MAX_BYTES:
            raise HTTPException(413, "Il modello deve essere un file .onnx tra 1 KB e 20 MB")
    return bytes(data)


async def _store_wakeword(request: Request) -> dict:
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/octet-stream":
        raise HTTPException(415, "Invia il modello come file binario")
    data = await _read_capped(request)
    if len(data) < 1024:
        raise HTTPException(400, "Il modello deve essere un file .onnx tra 1 KB e 20 MB")
    if data[:1] != b"\x08":
        raise HTTPException(400, "Il file non è un modello ONNX valido")
    WAKE_DIR.mkdir(parents=True, exist_ok=True)
    target = WAKE_DIR / "ehi_atena.onnx"
    tmp = target.with_name(f".{secrets.token_hex(8)}.part")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)
    store.event("INFO", "Modello «Ehi, Atena» caricato", "setup")
    if not DEMO:
        from orchestrator import orch
        from tasks import background
        background(orch.ensure(["ear"], "nuovo modello «Ehi, Atena»"))
    return {"ok": True}


def _parse_answers(text: str) -> dict:
    raw: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key in ANSWER_KEYS:
            raw[key] = value.strip().strip('"').strip("'")
    profile = next((k for k, v in PROFILES.items() if v["model"] and v["model"] == raw.get("ATENA_LLM_MODEL")), "auto")
    updates = _clean({"name": raw.get("ATENA_USER_NAME", ""), "lang": raw.get("ATENA_UI_LANG", "it"), "profile": profile,
                      "voice": raw.get("ATENA_VOICE", "if_sara"), "ha_url": raw.get("HOME_ASSISTANT_URL", ""),
                      "ha_token": raw.get("HOME_ASSISTANT_TOKEN", ""), "telegram": raw.get("ATENA_TELEGRAM_TOKEN", ""),
                      "commercial": raw.get("ATENA_COMMERCIAL") == "1"})
    smb = raw.get("ATENA_SMB_PASSWORD", "")
    if smb:
        if not SMB_RE.fullmatch(smb):
            raise HTTPException(400, "Password delle condivisioni non valida (almeno 12 caratteri, nessuno spazio)")
        updates["ATENA_SMB_PASSWORD"] = smb
    return updates


def answers_trusted(path: Path) -> bool:
    try:
        st = path.lstat()
    except OSError:
        return False
    if not path.is_file() or path.is_symlink():
        return False
    return DEMO or (st.st_uid == 0 and not st.st_mode & 0o022)


async def apply_answers_file(path: Path = ANSWERS_FILE) -> bool:
    if done() or not answers_trusted(path):
        return False
    try:
        updates = _parse_answers(path.read_text(encoding="utf-8"))
    except HTTPException as exc:
        store.event("ERROR", f"File di risposte non applicato: {exc.detail}", "setup")
        return False
    except (OSError, UnicodeDecodeError) as exc:
        store.event("ERROR", f"File di risposte illeggibile: {exc}", "setup")
        return False
    await _apply(updates, "file di risposte")
    _mark_done("file di risposte")
    try:
        path.unlink()
    except OSError:
        pass
    return True
