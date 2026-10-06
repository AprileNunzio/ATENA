import base64
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
APP_DIR = BACKEND_DIR.parent
DEMO = os.environ.get("ATENA_DEMO") == "1"
ATENA_DIR = Path(os.environ.get("ATENA_DIR", BACKEND_DIR.parents[1] if DEMO else "/opt/Atena"))
_ROOT = Path(tempfile.gettempdir()) / "atena-demo" if DEMO else Path("/")
STATE_DIR = _ROOT / "var/lib/atena"
ENV_FILE = _ROOT / "etc/atena/atena.env"
SAFE_FILE = STATE_DIR / "safe_mode.json"
REPAIR_FILE = STATE_DIR / "repair.json"
AUTO_STAMP = STATE_DIR / "safe_autorepair"
REPAIR_SCRIPT = ATENA_DIR / "scripts/os/repair.sh"
PAGE_FILE = APP_DIR / "web/safe/safe.html"
PUBLIC_PORT = int(os.environ.get("ATENA_PUBLIC_PORT", 8000 if DEMO else 80))
ADMIN_PORT = int(os.environ.get("ATENA_ADMIN_PORT", 8001 if DEMO else 8080))
AUTO_REPAIR_EVERY = 1800
REQUEST_GAP = 20
REPAIR_STALE = 3600

log = logging.getLogger("atena.safe")
_lock = threading.Lock()
_last_request = 0.0


def classify(exc: BaseException) -> str:
    if isinstance(exc, ImportError) and not isinstance(exc, SyntaxError):
        top = (getattr(exc, "name", None) or "").split(".")[0]
        local = bool(top) and (top == "features" or (BACKEND_DIR / f"{top}.py").exists() or (BACKEND_DIR / top).is_dir()
                               or (APP_DIR / top).is_dir())
        return "broken_code" if local or not top else "missing_library"
    if isinstance(exc, (SyntaxError, NameError, AttributeError, TypeError)):
        return "broken_code"
    if isinstance(exc, OSError):
        return "system"
    return "unknown"


def describe(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    text = text.replace(str(ATENA_DIR), "…")
    return re.sub(r"\s+", " ", text)[:300]


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def clear() -> None:
    try:
        SAFE_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        log.warning("Impossibile rimuovere %s", SAFE_FILE)


def ui_lang() -> str:
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("ATENA_UI_LANG="):
                value = line.split("=", 1)[1].strip()
                if re.fullmatch(r"[a-z]{2}", value):
                    return value
    except OSError:
        pass
    return "it"


def repair_running() -> bool:
    status = _read_json(REPAIR_FILE) or {}
    updated = status.get("updated")
    return status.get("state") == "running" and isinstance(updated, (int, float)) and time.time() - updated < REPAIR_STALE


def _repair_command() -> list[str]:
    script = ["/bin/bash", str(REPAIR_SCRIPT), "--quiet", "--origin=safe-mode"]
    runner = shutil.which("systemd-run")
    if runner:
        return [runner, "--unit=atena-repair", "--collect", "--quiet", "--property=TimeoutStartSec=3600", *script]
    return script


def start_repair() -> bool:
    if DEMO or not REPAIR_SCRIPT.is_file():
        return False
    try:
        subprocess.Popen(_repair_command(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    except OSError:
        log.exception("Avvio della riparazione non riuscito")
        return False
    return True


def request_repair() -> HTTPStatus:
    global _last_request
    with _lock:
        now = time.monotonic()
        if repair_running():
            return HTTPStatus.CONFLICT
        if _last_request and now - _last_request < REQUEST_GAP:
            return HTTPStatus.TOO_MANY_REQUESTS
        if not start_repair():
            return HTTPStatus.SERVICE_UNAVAILABLE
        _last_request = now
        return HTTPStatus.ACCEPTED


def auto_repair() -> bool:
    try:
        if AUTO_STAMP.exists() and time.time() - AUTO_STAMP.stat().st_mtime < AUTO_REPAIR_EVERY:
            return False
        AUTO_STAMP.parent.mkdir(parents=True, exist_ok=True)
        AUTO_STAMP.touch()
    except OSError:
        return False
    return request_repair() == HTTPStatus.ACCEPTED


def _hashes(page: str, tag: str) -> str:
    blocks = re.findall(rf"<{tag}>(.*?)</{tag}>", page, flags=re.S)
    return " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(b.encode()).digest()).decode()}'" for b in blocks)


def load_page() -> tuple[bytes, str]:
    try:
        page = PAGE_FILE.read_text(encoding="utf-8")
    except OSError:
        page = "<!DOCTYPE html><meta charset=utf-8><title>Atena</title><p>Atena: safe mode. sudo atenactl ripara</p>"
    csp = (f"default-src 'none'; script-src {_hashes(page, 'script') or chr(39) + 'none' + chr(39)}; "
           f"style-src {_hashes(page, 'style') or chr(39) + 'none' + chr(39)}; connect-src 'self'; img-src 'self' data:; "
           "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    return page.encode("utf-8"), csp


class SafeState:
    def __init__(self, reason: str, error: str) -> None:
        self.reason = reason
        self.error = error
        self.since = int(time.time())
        self.page, self.csp = load_page()

    def snapshot(self) -> dict:
        return {"safe_mode": True, "reason": self.reason, "error": self.error, "since": self.since,
                "lang": ui_lang(), "repair": _read_json(REPAIR_FILE)}


def handler_for(state: SafeState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Atena"
        sys_version = ""
        timeout = 15
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        def _send(self, status: HTTPStatus, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: HTTPStatus, data: dict) -> None:
            self._send(status, json.dumps(data).encode("utf-8"), "application/json")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                self._json(HTTPStatus.OK, {"ok": True, "safe_mode": True, "reason": state.reason})
            elif path == "/api/safe":
                self._json(HTTPStatus.OK, state.snapshot())
            elif path.startswith("/api/"):
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"safe_mode": True})
            else:
                self._send(HTTPStatus.OK, state.page, "text/html; charset=utf-8", {"Content-Security-Policy": state.csp})

        do_HEAD = do_GET

        def _same_origin(self) -> bool:
            if self.headers.get("X-Atena-Request") != "1":
                return False
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            host = self.headers.get("Host", "")
            return bool(host) and re.sub(r"^https?://", "", origin) == host

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/api/safe/repair":
                self._json(HTTPStatus.NOT_FOUND, {"ok": False})
                return
            if not self._same_origin():
                self._json(HTTPStatus.FORBIDDEN, {"ok": False})
                return
            status = request_repair()
            self._json(status, {"ok": status == HTTPStatus.ACCEPTED})

        def _not_allowed(self):
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False})

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_allowed

    return Handler


def serve(state: SafeState, ports: tuple[int, ...]) -> list[ThreadingHTTPServer]:
    servers = []
    for port in ports:
        server = ThreadingHTTPServer(("0.0.0.0", port), handler_for(state))
        server.daemon_threads = True
        servers.append(server)
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return servers


def run(exc: BaseException) -> None:
    reason, error = classify(exc), describe(exc)
    try:
        _write_json(SAFE_FILE, {"reason": reason, "error": error, "since": int(time.time())})
    except OSError:
        log.exception("Impossibile salvare lo stato della modalità sicura")
    state = SafeState(reason, error)
    servers = serve(state, (PUBLIC_PORT, ADMIN_PORT))
    log.warning("Modalità sicura attiva (%s): %s", reason, error)
    if auto_repair():
        log.warning("Riparazione automatica avviata")
    servers[0].serve_forever()
