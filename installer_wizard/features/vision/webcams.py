import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from config import STATE_DIR, env_get
from state import store

from features.vision import devices as dev

log = logging.getLogger("atena.webcams")
STATE_FILE = STATE_DIR / "webcams.json"
IR_STATUS_FILE = STATE_DIR / "ir_status.json"
SCAN_EVERY = 10.0
USB_DEVICES = Path("/sys/bus/usb/devices")
UVC_DRIVER = Path("/sys/bus/usb/drivers/uvcvideo")


def run_v4l(args: list[str], timeout: float = 8.0) -> str:
    exe = shutil.which("v4l2-ctl")
    if not exe:
        raise FileNotFoundError("v4l-utils non installato")
    result = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, check=False)
    return result.stdout


def inspect(path: str) -> tuple[dict, dict]:
    info = dev.parse_info(run_v4l(["-d", path, "--info"]))
    formats = dev.parse_formats(run_v4l(["-d", path, "--list-formats-ext"]))
    return info, formats


def usb_video_interfaces(root: Path = USB_DEVICES) -> list[dict]:
    found = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return found
    for entry in entries:
        try:
            if (entry / "bInterfaceClass").read_text(encoding="utf-8").strip() != dev.USB_CLASS_VIDEO:
                continue
            parent = entry.parent / entry.name.split(":")[0]
            found.append({"bus": entry.name, "vendor": (parent / "idVendor").read_text(encoding="utf-8").strip(),
                          "product": (parent / "idProduct").read_text(encoding="utf-8").strip(),
                          "name": (parent / "product").read_text(encoding="utf-8").strip() if (parent / "product").exists() else ""})
        except OSError:
            continue
    return found


def ensure_driver(modprobe=None) -> str:
    if UVC_DRIVER.exists():
        return "uvcvideo già attivo"
    exe = modprobe or shutil.which("modprobe")
    if not exe:
        return "modprobe non disponibile"
    result = subprocess.run([exe, "uvcvideo"], capture_output=True, text=True, timeout=20, check=False)
    return "uvcvideo caricato senza riavviare" if result.returncode == 0 else f"uvcvideo non caricabile: {result.stderr.strip()[:120]}"


def overrides() -> tuple[str, str]:
    return env_get("ATENA_CAMERA_RGB", "auto").strip() or "auto", env_get("ATENA_CAMERA_IR", "auto").strip() or "auto"


def scan(inspector=inspect, lister=None, usb=usb_video_interfaces, driver=ensure_driver) -> dict:
    problems, driver_note = [], ""
    try:
        listing = (lister or (lambda: run_v4l(["--list-devices"])))()
        devices = dev.build(dev.parse_list(listing), inspector)
    except FileNotFoundError as exc:
        devices, problems = [], [str(exc)]
    except (subprocess.SubprocessError, OSError) as exc:
        devices, problems = [], [f"scansione delle webcam non riuscita: {exc}"]
    present = usb()
    if present and not devices and not problems:
        driver_note = driver()
        problems.append(f"Una periferica video USB è collegata ma non ha nodi video ({driver_note})")
    for cam in present:
        if not any(d["vendor"] == cam["vendor"] and d["product"] == cam["product"] for d in devices) and devices:
            problems.append(f"{cam['name'] or cam['vendor'] + ':' + cam['product']} è collegata ma il kernel non espone un flusso video")
    rgb_override, ir_override = overrides()
    return {"updated": time.time(), "devices": devices, "selected": dev.choose(devices, rgb_override, ir_override),
            "usb_video": present, "problems": problems, "driver": driver_note,
            "tools": {"v4l2-ctl": bool(shutil.which("v4l2-ctl"))}}


def describe(d: dict) -> str:
    rgb = d.get("rgb_mode") or {}
    text = f"RGB {rgb.get('width', '?')}x{rgb.get('height', '?')}" if d.get("rgb") else "senza sensore a colori"
    if d.get("has_ir"):
        ir = d.get("ir_mode") or {}
        text += f" + infrarossi {ir.get('width', '?')}x{ir.get('height', '?')}"
    return text


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("%s non leggibile: %s", path.name, exc)
        return {}


class Webcams:

    def __init__(self) -> None:
        self.state = read_json(STATE_FILE)
        self.sig = dev.signature(self.state.get("devices", []))

    @staticmethod
    def enabled() -> bool:
        return env_get("ATENA_VISION", "1") != "0"

    def publish(self, new: dict) -> None:
        before = {d["id"]: d for d in self.state.get("devices", [])}
        after = {d["id"]: d for d in new["devices"]}
        for key, d in after.items():
            if key not in before:
                store.event("INFO", f"Webcam collegata: {d['name']} ({describe(d)})", "vision")
                self.notify(d)
        for key, d in before.items():
            if key not in after:
                store.event("INFO", f"Webcam scollegata: {d['name']}", "vision")
        for problem in new["problems"]:
            if problem not in self.state.get("problems", []):
                store.event("WARN", f"Webcam: {problem}", "vision")
        self.state = new
        self.sig = dev.signature(new["devices"])
        store.webcams = {"devices": len(new["devices"]), "ir": any(d["has_ir"] for d in new["devices"]),
                         "selected": new["selected"].get("device")}
        store.touch()
        self.write(new)

    @staticmethod
    def notify(d: dict) -> None:
        from features.desktop.desk import desk
        text = (f"Ho riconosciuto {d['name']}: {describe(d)}. "
                + ("Uso anche l'infrarosso per riconoscerti meglio e distinguere una foto da una persona." if d["has_ir"] else ""))
        desk.show("notice", {"icon": "📷", "title": "Nuova webcam", "text": text.strip()}, key=f"webcam:{d['id']}", ttl=120)

    @staticmethod
    def write(state: dict) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(state), encoding="utf-8")
            os.replace(tmp, STATE_FILE)
        except OSError as exc:
            log.warning("Stato delle webcam non salvato: %s", exc)

    async def refresh(self, force: bool = False) -> dict:
        new = await asyncio.to_thread(scan)
        changed = dev.signature(new["devices"]) != self.sig or new["problems"] != self.state.get("problems", [])
        if changed or force or not self.state:
            self.publish(new)
        else:
            self.state["updated"] = new["updated"]
        return self.state

    def view(self) -> dict:
        return {**self.state, "ir_status": read_json(IR_STATUS_FILE)}

    async def run(self) -> None:
        while True:
            try:
                if self.enabled():
                    await self.refresh()
            except Exception:
                log.exception("Controllo delle webcam non riuscito")
            await asyncio.sleep(SCAN_EVERY)


webcams = Webcams()
