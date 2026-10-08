import base64
import json
import logging
import os
import re
import socket

from settings import paths, protect

log = logging.getLogger("atena.settings")

DEFAULTS = {
    "server": "", "node_id": "", "token": "", "pin": "", "ca": "", "name": socket.gethostname(),
    "hotkey": "ctrl+alt+space", "voice": True, "headset": False,
    "mic_device": None, "orb_x": None, "orb_y": None,
    "backup_folders": [], "backup_target": "", "backup_hours": 24,
}
SEALED = "dpapi:"


def _seal(token: str) -> str:
    return SEALED + base64.b64encode(protect.seal(token.encode())).decode() if token else ""


def _unseal(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(SEALED):
        log.warning("Token salvato in chiaro: verrà cifrato al prossimo salvataggio")
        return value
    return protect.unseal(base64.b64decode(value[len(SEALED):])).decode()


def _read_json() -> dict:
    if not paths.CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(paths.CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        broken = paths.CONFIG_FILE.with_suffix(".broken")
        os.replace(paths.CONFIG_FILE, broken)
        log.error("Impostazioni illeggibili (%s): spostate in %s, ripristino i valori predefiniti", exc, broken)
        return {}
    return data if isinstance(data, dict) else {}


def _bootstrap_server() -> str:
    seed = paths.APP_DIR / "server.txt"
    return normalize_server(seed.read_text(encoding="utf-8")) if seed.is_file() else ""


def load() -> dict:
    paths.ensure()
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in _read_json().items() if k in DEFAULTS})
    cfg["token"] = _unseal(str(cfg.get("token") or ""))
    cfg["server"] = cfg["server"] or _bootstrap_server()
    return cfg


def save(cfg: dict) -> None:
    paths.ensure()
    data = {k: cfg.get(k, v) for k, v in DEFAULTS.items()}
    data["token"] = _seal(str(cfg.get("token") or ""))
    tmp = paths.CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, paths.CONFIG_FILE)


def node_id_for(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "pc"
    return ("pc-" + slug)[:40]


def normalize_server(value: str) -> str:
    value = value.strip().rstrip("/")
    if value and not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    if value and not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d{1,5})?", value):
        raise ValueError("Indirizzo di ATENA non valido: usa solo nome o IP, ad esempio 192.168.1.100")
    return value
