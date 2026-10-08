"""Impostazioni locali dell'assistente, in %APPDATA%\\ATENA. Il token del nodo è cifrato con DPAPI
(leggibile solo dall'utente Windows che l'ha salvato)."""
import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import socket
import sys
from pathlib import Path

VERSION = "1.0.0"
DIR = Path(os.environ.get("APPDATA") or Path.home()) / "ATENA"
FILE = DIR / "assistant.json"
APP_DIR = Path(__file__).resolve().parent
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ATENA Assistente"

DEFAULTS = {
    "server": "", "node_id": "", "token": "", "name": socket.gethostname(),
    "hotkey": "ctrl+alt+space", "wake": True, "headset": False, "webcam": True, "voice": True,
    "mic_device": None, "orb_x": None, "orb_y": None, "extra_folders": [],
}


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in, blob_out = _Blob(len(data), buf), _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError("DPAPI non disponibile")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _seal(token: str) -> str:
    if not token or sys.platform != "win32":
        return token
    return "dpapi:" + base64.b64encode(_dpapi(token.encode(), True)).decode()


def _open(value: str) -> str:
    if not value.startswith("dpapi:"):
        return value
    try:
        return _dpapi(base64.b64decode(value[6:]), False).decode()
    except (OSError, ValueError):
        return ""


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    cfg["token"] = _open(str(cfg.get("token") or ""))
    if not cfg["server"]:
        try:  # scritto da ATENA nello ZIP scaricato: l'utente non deve cercare l'indirizzo
            cfg["server"] = (APP_DIR / "server.txt").read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return cfg


def save(cfg: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    data = {k: cfg.get(k, v) for k, v in DEFAULTS.items()}
    data["token"] = _seal(str(cfg.get("token") or ""))
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, FILE)


def node_id_for(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "pc"
    return ("pc-" + slug)[:40]


def normalize_server(value: str) -> str:
    value = value.strip().rstrip("/")
    if value and not re.match(r"^https?://", value, re.I):
        value = "http://" + value
    return value


def autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
        return True
    except OSError:
        return False


def set_autostart(on: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            exe = pythonw if pythonw.exists() else Path(sys.executable)
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, f'"{exe}" "{APP_DIR / "atena_assistant.py"}"')
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass
