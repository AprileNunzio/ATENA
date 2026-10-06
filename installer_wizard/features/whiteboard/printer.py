# flake8: noqa: E501
import json
import os
import platform
import re
import socket
import subprocess
import tempfile
import time
import urllib.request

from config import STATE_DIR
from features.whiteboard.board import board
from features.whiteboard.pdf_exporter import export_pages_to_pdf

PRINTERS_FILE = STATE_DIR / "printers.json"


class PrinterManager:
    def __init__(self) -> None:
        self.custom_printers: list[dict] = []
        self.load()

    def load(self) -> None:
        try:
            if PRINTERS_FILE.exists():
                data = json.loads(PRINTERS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.custom_printers = data
        except Exception:
            self.custom_printers = []

    def save(self) -> None:
        try:
            PRINTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = PRINTERS_FILE.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.custom_printers, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(PRINTERS_FILE)
        except Exception:
            pass

    def add_printer(self, p: dict) -> dict:
        pid = str(p.get("id") or f"p_{int(time.time() * 1000)}")
        item = {
            "id": pid,
            "name": str(p.get("name") or "Nuova Stampante").strip(),
            "type": p.get("type", "laser_2d"),
            "connection": p.get("connection", "network"),
            "address": str(p.get("address") or "").strip(),
            "port": int(p.get("port", 9100)),
            "api_key": str(p.get("api_key") or "").strip(),
        }
        self.custom_printers = [x for x in self.custom_printers if x.get("id") != pid]
        self.custom_printers.append(item)
        self.save()
        return item

    def remove_printer(self, pid: str) -> bool:
        initial = len(self.custom_printers)
        self.custom_printers = [x for x in self.custom_printers if x.get("id") != pid]
        if len(self.custom_printers) != initial:
            self.save()
            return True
        return False

    def _discover_os_printers(self) -> list[dict]:
        found = []
        is_win = platform.system().lower() == "windows"
        if is_win:
            try:
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Printer | Select-Object Name, PortName, Default | ConvertTo-Json -Compress",
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0 and res.stdout.strip():
                    try:
                        raw = json.loads(res.stdout)
                        items = raw if isinstance(raw, list) else [raw]
                        for item in items:
                            nm = str(item.get("Name", ""))
                            pt = str(item.get("PortName", ""))
                            if not nm:
                                continue
                            kind = (
                                "inkjet_2d"
                                if any(
                                    w in nm.lower()
                                    for w in ["ink", "deskjet", "ecotank", "pixma"]
                                )
                                else "laser_2d"
                            )
                            conn = (
                                "network"
                                if (
                                    "." in pt
                                    or "ip" in pt.lower()
                                    or "http" in pt.lower()
                                )
                                else "usb"
                            )
                            found.append(
                                {
                                    "id": f"win_{re.sub(r'[^a-zA-Z0-9_]', '_', nm)}",
                                    "name": nm,
                                    "type": kind,
                                    "connection": conn,
                                    "address": pt,
                                    "is_default": bool(item.get("Default", False)),
                                    "status": "ready",
                                }
                            )
                    except json.JSONDecodeError:
                        pass  # Nessuna stampante trovata o output JSON non valido
            except Exception:
                pass
        else:
            try:
                res = subprocess.run(
                    ["lpstat", "-p", "-d"], capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        m = re.search(r"printer\s+([^\s]+)", line)
                        if m:
                            nm = m.group(1)
                            kind = (
                                "inkjet_2d"
                                if any(
                                    w in nm.lower()
                                    for w in ["ink", "deskjet", "ecotank", "pixma"]
                                )
                                else "laser_2d"
                            )
                            found.append(
                                {
                                    "id": f"cups_{nm}",
                                    "name": nm,
                                    "type": kind,
                                    "connection": "system",
                                    "address": f"cups://{nm}",
                                    "status": "ready",
                                }
                            )
            except Exception:
                pass
        return found

    def list_printers(self) -> list[dict]:
        os_printers = self._discover_os_printers()
        defaults = [
            {
                "id": "pdf_export",
                "name": "Esporta Documento PDF (Archivio)",
                "type": "virtual_pdf",
                "connection": "virtual",
                "status": "ready",
            },
            {
                "id": "laser_grbl_local",
                "name": "Incisore Laser GRBL (USB / Seriale)",
                "type": "engraver",
                "connection": "usb",
                "address": "/dev/ttyUSB0",
                "status": "standby",
            },
            {
                "id": "klipper_3d_local",
                "name": "Stampante 3D Klipper / Moonraker",
                "type": "3d",
                "connection": "network",
                "address": "http://127.0.0.1:7125",
                "status": "standby",
            },
        ]
        all_p = {p["id"]: p for p in defaults}
        for op in os_printers:
            all_p[op["id"]] = op
        for cp in self.custom_printers:
            all_p[cp["id"]] = cp
        return list(all_p.values())

    def generate_grbl_gcode(
        self, pages: list[dict], power: int = 400, feed: int = 1200
    ) -> str:
        lines = ["G21", "G90", "M5", "G0 Z0 F1000", "G0 X0 Y0 F2000"]
        scale_x = 200.0 / 1600.0
        scale_y = 112.5 / 900.0
        for page in pages:
            for it in page.get("items", []):
                t = it.get("type")
                if t in ("stroke", "erase") and t != "erase":
                    pts = it.get("points", [])
                    if len(pts) >= 2:
                        first = pts[0]
                        lines.append(
                            f"G0 X{first[0] * scale_x:.2f} Y{(900 - first[1]) * scale_y:.2f}"
                        )
                        lines.append(f"M3 S{power}")
                        for p in pts[1:]:
                            lines.append(
                                f"G1 X{p[0] * scale_x:.2f} Y{(900 - p[1]) * scale_y:.2f} F{feed}"
                            )
                        lines.append("M5")
                elif t in ("line", "arrow"):
                    x1, y1 = it.get("x1", 0), it.get("y1", 0)
                    x2, y2 = it.get("x2", 0), it.get("y2", 0)
                    lines.append(f"G0 X{x1 * scale_x:.2f} Y{(900 - y1) * scale_y:.2f}")
                    lines.append(f"M3 S{power}")
                    lines.append(
                        f"G1 X{x2 * scale_x:.2f} Y{(900 - y2) * scale_y:.2f} F{feed}"
                    )
                    lines.append("M5")
                elif t == "rect":
                    x1, y1 = it.get("x1", 0), it.get("y1", 0)
                    x2, y2 = it.get("x2", 0), it.get("y2", 0)
                    lines.append(f"G0 X{x1 * scale_x:.2f} Y{(900 - y1) * scale_y:.2f}")
                    lines.append(f"M3 S{power}")
                    lines.append(
                        f"G1 X{x2 * scale_x:.2f} Y{(900 - y1) * scale_y:.2f} F{feed}"
                    )
                    lines.append(
                        f"G1 X{x2 * scale_x:.2f} Y{(900 - y2) * scale_y:.2f} F{feed}"
                    )
                    lines.append(
                        f"G1 X{x1 * scale_x:.2f} Y{(900 - y2) * scale_y:.2f} F{feed}"
                    )
                    lines.append(
                        f"G1 X{x1 * scale_x:.2f} Y{(900 - y1) * scale_y:.2f} F{feed}"
                    )
                    lines.append("M5")
        lines.append("M5")
        lines.append("G0 X0 Y0 F2000")
        return "\n".join(lines)

    def generate_3d_gcode(self, pages: list[dict]) -> str:
        lines = [
            "G28",
            "M104 S205",
            "M140 S60",
            "M190 S60",
            "M109 S205",
            "G92 E0",
            "G1 Z0.3 F1000",
            "G1 X10 Y10 F3000",
        ]
        scale_x = 180.0 / 1600.0
        scale_y = 100.0 / 900.0
        e_pos = 0.0
        for page in pages:
            for it in page.get("items", []):
                pts = it.get("points", [])
                if it.get("type") == "stroke" and len(pts) >= 2:
                    p0 = pts[0]
                    lines.append(
                        f"G0 X{20 + p0[0] * scale_x:.2f} Y{20 + (900 - p0[1]) * scale_y:.2f} F3000"
                    )
                    for p in pts[1:]:
                        e_pos += 0.05
                        lines.append(
                            f"G1 X{20 + p[0] * scale_x:.2f} Y{20 + (900 - p[1]) * scale_y:.2f} E{e_pos:.3f} F1200"
                        )
        lines.extend(["G92 E0", "G1 E-2 F1800", "G1 Z20 F1000", "G28 X0 Y0", "M84"])
        return "\n".join(lines)

    @staticmethod
    def lp_options(opts: dict) -> list[str]:
        args = ["-n", str(max(1, min(99, int(opts.get("copies", 1) or 1))))]
        if opts.get("paper") in ("A4", "A3", "A5", "Letter", "Legal"):
            args += ["-o", f"media={opts['paper']}"]
        args += ["-o", "sides=two-sided-long-edge" if opts.get("duplex") else "sides=one-sided"]
        if opts.get("orientation") == "landscape":
            args += ["-o", "orientation-requested=4"]
        if opts.get("color") is False:
            args += ["-o", "print-color-mode=monochrome"]
        quality = {"draft": "3", "normal": "4", "high": "5"}.get(str(opts.get("quality")))
        if quality:
            args += ["-o", f"print-quality={quality}"]
        return args

    def print_job(self, printer_id: str, options: dict | None = None) -> dict:
        opts = options or {}
        printers = {p["id"]: p for p in self.list_printers()}
        p = printers.get(printer_id)
        if not p:
            raise ValueError("Stampante non trovata")
        p_type = p.get("type")
        pdf_bytes = export_pages_to_pdf(board.pages)
        if p_type == "virtual_pdf":
            out_path = STATE_DIR / f"lavagna_{int(time.time())}.pdf"
            out_path.write_bytes(pdf_bytes)
            return {
                "status": "ok",
                "message": f"PDF salvato con successo in {out_path.name}",
                "file": str(out_path),
            }
        if p_type in ("laser_2d", "inkjet_2d"):
            conn = p.get("connection")
            if conn == "network" and p.get("address"):
                host = p["address"]
                port = int(p.get("port", 9100))
                try:
                    with socket.create_connection((host, port), timeout=6) as s:
                        s.sendall(pdf_bytes)
                    return {
                        "status": "ok",
                        "message": f"Inviato alla stampante di rete {p['name']} ({host}:{port})",
                    }
                except Exception as exc:
                    raise RuntimeError(f"Errore connessione stampante di rete: {exc}")
            is_win = platform.system().lower() == "windows"
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            try:
                if is_win:
                    p_name = p.get("name", "")
                    ps_cmd = (
                        f"Start-Process -FilePath '{tmp_path}' -Verb PrintTo -ArgumentList '\"{p_name}\"' -Wait"
                        if p_name
                        else f"Start-Process -FilePath '{tmp_path}' -Verb Print -Wait"
                    )
                    res = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_cmd],
                        capture_output=True,
                        timeout=30,
                    )
                    if res.returncode != 0:
                        raise RuntimeError(res.stderr)
                else:
                    cups_name = p.get("name", "")
                    cmd = ["lp", *(["-d", cups_name] if cups_name else []), *self.lp_options(opts), tmp_path]
                    res = subprocess.run(cmd, capture_output=True, timeout=30)
                    if res.returncode != 0:
                        raise RuntimeError(res.stderr)
            finally:
                try:
                    # Rimuoviamo il tempfile solo dopo che il processo ha finito
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return {
                "status": "ok",
                "message": f"Lavoro di stampa inviato a {p['name']}",
            }
        if p_type == "engraver":
            power = int(opts.get("laser_power", 400))
            feed = int(opts.get("laser_feed", 1200))
            gcode = self.generate_grbl_gcode(board.pages, power, feed)
            if p.get("connection") == "network" and p.get("address"):
                try:
                    with socket.create_connection(
                        (p["address"], int(p.get("port", 8080))), timeout=5
                    ) as s:
                        s.sendall(gcode.encode("utf-8"))
                    return {
                        "status": "ok",
                        "message": f"G-code laser inviato con successo a {p['name']}",
                    }
                except Exception as exc:
                    raise RuntimeError(f"Errore invio incisore laser di rete: {exc}")
            out_file = STATE_DIR / f"laser_{int(time.time())}.nc"
            out_file.write_text(gcode, encoding="utf-8")
            return {
                "status": "ok",
                "message": f"G-code per taglio/incisione generato: {out_file.name}",
                "file": str(out_file),
            }
        if p_type == "3d":
            gcode = self.generate_3d_gcode(board.pages)
            addr = str(p.get("address", ""))
            if addr.startswith("http"):
                try:
                    endpoint = f"{addr.rstrip('/')}/server/files/upload"
                    req = urllib.request.Request(
                        endpoint,
                        data=gcode.encode("utf-8"),
                        headers={"Content-Type": "text/plain"},
                    )
                    with urllib.request.urlopen(req, timeout=8):
                        pass
                    return {
                        "status": "ok",
                        "message": f"G-code inviato a {p['name']} ({addr})",
                    }
                except Exception:
                    pass
            out_file = STATE_DIR / f"3d_print_{int(time.time())}.gcode"
            out_file.write_text(gcode, encoding="utf-8")
            return {
                "status": "ok",
                "message": f"G-code 3D generato: {out_file.name}",
                "file": str(out_file),
            }
        raise ValueError(f"Tipo di stampante non supportato: {p_type}")


printer_manager = PrinterManager()
