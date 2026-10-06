import asyncio
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import threading

import httpx

from config import STATE_DIR

from features.whiteboard.printer import printer_manager

OPTIONS_FILE = STATE_DIR / "printer_options.json"
TYPES = ("laser_2d", "inkjet_2d", "3d", "engraver", "virtual_pdf")
CONNECTIONS = ("network", "usb", "system", "virtual")
PAPER = ("A4", "A3", "A5", "Letter", "Legal")
ORIENTATION = ("portrait", "landscape")
QUALITY = ("draft", "normal", "high")
SCAN_PORTS = {9100: "jetdirect", 631: "ipp", 515: "lpd"}
NAME_RE = re.compile(r"^[\w .,()'+-]{1,60}$", re.U)
HOST_RE = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
SERIAL_RE = re.compile(r"^(/dev/tty(USB|ACM|S|AMA)\d{1,3}|COM\d{1,3})$")
URL_RE = re.compile(r"^https?://[^\s/@]+(:\d{1,5})?(/[^\s]*)?$")
QUEUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
PROBE_TIMEOUT = 1.5
SCAN_TIMEOUT = 0.4
SCAN_LIMIT = 64


class PrinterError(ValueError):
    pass


def _clean_name(value) -> str:
    name = " ".join(str(value or "").split())
    if not NAME_RE.match(name):
        raise PrinterError("printers.error.name")
    return name


def _clean_address(connection: str, value) -> str:
    address = str(value or "").strip()
    if connection == "usb":
        if not SERIAL_RE.match(address):
            raise PrinterError("printers.error.serial")
        return address
    if URL_RE.match(address):
        return address
    try:
        ipaddress.ip_address(address)
        return address
    except ValueError:
        pass
    if not HOST_RE.match(address):
        raise PrinterError("printers.error.address")
    return address


def validate(body: dict) -> dict:
    kind = str(body.get("type") or "")
    connection = str(body.get("connection") or "")
    if kind not in TYPES or kind == "virtual_pdf":
        raise PrinterError("printers.error.type")
    if connection not in ("network", "usb"):
        raise PrinterError("printers.error.connection")
    try:
        port = int(body.get("port") or (7125 if kind == "3d" else 9100))
    except (TypeError, ValueError):
        raise PrinterError("printers.error.port")
    if not 1 <= port <= 65535:
        raise PrinterError("printers.error.port")
    return {"name": _clean_name(body.get("name")), "type": kind, "connection": connection,
            "address": _clean_address(connection, body.get("address")), "port": port,
            "api_key": str(body.get("api_key") or "").strip()[:200]}


def _bounded(value, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def clean_options(body: dict) -> dict:
    return {
        "paper": body.get("paper") if body.get("paper") in PAPER else "A4",
        "orientation": body.get("orientation") if body.get("orientation") in ORIENTATION else "portrait",
        "quality": body.get("quality") if body.get("quality") in QUALITY else "normal",
        "color": bool(body.get("color", True)),
        "duplex": bool(body.get("duplex", False)),
        "copies": _bounded(body.get("copies"), 1, 99, 1),
        "laser_power": _bounded(body.get("laser_power"), 0, 1000, 400),
        "laser_feed": _bounded(body.get("laser_feed"), 10, 10000, 1200),
        "nozzle_temp": _bounded(body.get("nozzle_temp"), 0, 300, 205),
        "bed_temp": _bounded(body.get("bed_temp"), 0, 120, 60),
    }


class Printers:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        data = self._load()
        meta = data.pop("__default__", {})
        self.default_id = str(meta.get("id", "")) if isinstance(meta, dict) else ""
        self.options: dict[str, dict] = {k: v for k, v in data.items() if isinstance(v, dict)}

    @staticmethod
    def _load() -> dict:
        try:
            data = json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        payload = {**self.options, "__default__": {"id": self.default_id}}
        OPTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = OPTIONS_FILE.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
        os.replace(tmp, OPTIONS_FILE)

    @staticmethod
    def _custom_ids() -> set[str]:
        return {p.get("id") for p in printer_manager.custom_printers}

    def listing(self) -> list[dict]:
        custom = self._custom_ids()
        out = []
        for p in printer_manager.list_printers():
            safe = {k: v for k, v in p.items() if k != "api_key"}
            safe["has_api_key"] = bool(p.get("api_key"))
            safe["custom"] = p.get("id") in custom
            safe["options"] = clean_options(self.options.get(p["id"], {}))
            safe["atena_default"] = p["id"] == self.default_id
            out.append(safe)
        return out

    def find(self, pid: str) -> dict:
        for p in printer_manager.list_printers():
            if p.get("id") == pid:
                return p
        raise KeyError(pid)

    def add(self, body: dict) -> dict:
        item = printer_manager.add_printer(validate(body))
        return {k: v for k, v in item.items() if k != "api_key"}

    def remove(self, pid: str) -> bool:
        if pid not in self._custom_ids():
            raise PrinterError("printers.error.not_custom")
        with self.lock:
            self.options.pop(pid, None)
            if self.default_id == pid:
                self.default_id = ""
            self._save()
        return printer_manager.remove_printer(pid)

    def set_options(self, pid: str, body: dict) -> dict:
        self.find(pid)
        options = clean_options(body)
        with self.lock:
            self.options[pid] = options
            if body.get("atena_default"):
                self.default_id = pid
            elif self.default_id == pid:
                self.default_id = ""
            self._save()
        return options

    async def probe(self, pid: str) -> dict:
        p = self.find(pid)
        kind, connection, address = p.get("type"), p.get("connection"), str(p.get("address") or "")
        if connection == "virtual":
            return {"state": "ready", "detail": "printers.probe.virtual"}
        if connection == "system":
            return await asyncio.to_thread(self._probe_system, p)
        if connection == "usb":
            return {"state": "ready" if os.path.exists(address) else "offline", "detail": "printers.probe.serial"}
        if kind == "3d" and address.startswith("http"):
            try:
                async with httpx.AsyncClient(timeout=PROBE_TIMEOUT * 2) as client:
                    r = await client.get(f"{address.rstrip('/')}/printer/info")
                state = (r.json().get("result") or {}).get("state", "unknown") if r.status_code == 200 else "offline"
                return {"state": "ready" if state == "ready" else state, "detail": "printers.probe.moonraker"}
            except (httpx.HTTPError, ValueError):
                return {"state": "offline", "detail": "printers.probe.moonraker"}
        host = re.sub(r"^https?://", "", address).split("/")[0].split(":")[0]
        port = int(p.get("port") or 9100)
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), PROBE_TIMEOUT)
            writer.close()
            return {"state": "ready", "detail": "printers.probe.tcp"}
        except (OSError, asyncio.TimeoutError):
            return {"state": "offline", "detail": "printers.probe.tcp"}

    @staticmethod
    def _probe_system(p: dict) -> dict:
        if platform.system().lower() == "windows":
            return {"state": p.get("status", "ready"), "detail": "printers.probe.windows"}
        queue = str(p.get("name") or "")
        if not shutil.which("lpstat") or not QUEUE_RE.match(queue):
            return {"state": "unknown", "detail": "printers.probe.cups_missing"}
        try:
            out = subprocess.run(["lpstat", "-p", queue], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return {"state": "unknown", "detail": "printers.probe.cups_missing"}
        if "disabled" in out:
            return {"state": "offline", "detail": "printers.probe.cups"}
        return {"state": "busy" if "printing" in out else "ready", "detail": "printers.probe.cups"}

    async def discover(self) -> dict:
        found: dict[str, dict] = {}
        system = await asyncio.to_thread(self._cups_devices)
        for uri, label in system:
            found[uri] = {"uri": uri, "label": label, "source": "cups"}
        for host, port in await self._scan_subnet():
            scheme = SCAN_PORTS[port]
            uri = {"ipp": f"ipp://{host}/ipp/print", "jetdirect": f"socket://{host}:9100", "lpd": f"lpd://{host}/queue"}[scheme]
            found.setdefault(uri, {"uri": uri, "label": f"{host} ({scheme})", "source": "scan", "host": host, "port": port})
        return {"devices": sorted(found.values(), key=lambda d: d["uri"]), "can_install": self.can_install()}

    @staticmethod
    def _cups_devices() -> list[tuple[str, str]]:
        if not shutil.which("lpinfo"):
            return []
        try:
            out = subprocess.run(["lpinfo", "-l", "-v", "--timeout", "8"], capture_output=True, text=True, timeout=15).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        devices, uri = [], ""
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Device:"):
                uri = line.split("uri =", 1)[-1].strip()
            elif line.startswith("info =") and uri and "://" in uri:
                devices.append((uri, line.split("=", 1)[1].strip()))
                uri = ""
        return devices[:SCAN_LIMIT]

    @staticmethod
    def _local_network() -> ipaddress.IPv4Network | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("10.255.255.255", 1))
                address = ipaddress.ip_address(s.getsockname()[0])
        except OSError:
            return None
        if not address.is_private or address.is_loopback:
            return None
        return ipaddress.ip_network(f"{address}/24", strict=False)

    async def _scan_subnet(self) -> list[tuple[str, int]]:
        network = self._local_network()
        if network is None:
            return []
        gate = asyncio.Semaphore(128)

        async def knock(host: str, port: int):
            async with gate:
                try:
                    _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), SCAN_TIMEOUT)
                    writer.close()
                    return host, port
                except (OSError, asyncio.TimeoutError):
                    return None

        hits = await asyncio.gather(*(knock(str(h), p) for h in network.hosts() for p in SCAN_PORTS))
        return [h for h in hits if h][:SCAN_LIMIT]

    @staticmethod
    def can_install() -> bool:
        return platform.system().lower() != "windows" and bool(shutil.which("lpadmin"))

    def install(self, body: dict) -> dict:
        if not self.can_install():
            raise PrinterError("printers.error.install_unavailable")
        uri = str(body.get("uri") or "")
        if not re.match(r"^(ipp|ipps)://[A-Za-z0-9.-]+(:\d{1,5})?/[A-Za-z0-9/_.-]*$", uri):
            raise PrinterError("printers.error.uri")
        queue = str(body.get("queue") or "")
        if not QUEUE_RE.match(queue):
            raise PrinterError("printers.error.queue")
        try:
            res = subprocess.run(["lpadmin", "-p", queue, "-E", "-v", uri, "-m", "everywhere"],
                                 capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            raise PrinterError("printers.error.install_failed")
        if res.returncode != 0:
            raise PrinterError("printers.error.install_failed")
        return {"queue": queue, "uri": uri}


printers = Printers()
