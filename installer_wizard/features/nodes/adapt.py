import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time

from config import STATE_DIR
from state import store

from features.governor import profile

log = logging.getLogger("atena.nodes")
SNAPSHOT = STATE_DIR / "hardware_master.json"
LISTS = {"cameras": "Webcam", "audio_in": "Microfono", "audio_out": "Uscita audio", "usb": "Periferica USB"}
NUMBERS = (("cores", 1, 512), ("ram_gb", 0, 4096), ("disk_gb", 0, 1_000_000))
TEXT_RE = re.compile(r"[^\w\s.,:;@()/+\-'’àèéìòù]", re.U)
HISTORY = 12


def text(value, limit: int = 60) -> str:
    return TEXT_RE.sub("", str(value or "")).strip()[:limit]


def clean_hardware(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    out: dict = {}
    for key, lo, hi in NUMBERS:
        try:
            out[key] = round(max(lo, min(hi, float(raw.get(key) or 0))), 1)
        except (TypeError, ValueError):
            out[key] = 0
    out.update(avx2=bool(raw.get("avx2")), ir_camera=bool(raw.get("ir_camera")), bluetooth=bool(raw.get("bluetooth")),
               arch=text(raw.get("arch"), 20), gpu=text(raw.get("gpu")), os=text(raw.get("os")))
    for key in LISTS:
        items = raw.get(key) if isinstance(raw.get(key), list) else []
        out[key] = [text(i) for i in items[:12] if text(i)]
    return out


def diff(old: dict | None, new: dict) -> list[str]:
    if not old:
        return []
    changes = []
    for key, label in LISTS.items():
        before, after = set(old.get(key, [])), set(new.get(key, []))
        changes += [f"{label} collegato: {name}" for name in sorted(after - before)]
        changes += [f"{label} scollegato: {name}" for name in sorted(before - after)]
    if bool(old.get("ir_camera")) != bool(new.get("ir_camera")):
        changes.append("Sensore infrarosso collegato" if new.get("ir_camera") else "Sensore infrarosso scollegato")
    if old.get("gpu") != new.get("gpu"):
        changes.append(f"Scheda video: {new.get('gpu') or 'nessuna'}")
    if abs(float(old.get("ram_gb", 0)) - float(new.get("ram_gb", 0))) >= 0.5:
        changes.append(f"Memoria: da {old.get('ram_gb')} a {new.get('ram_gb')} GB")
    if old.get("cores") != new.get("cores"):
        changes.append(f"Processore: da {old.get('cores')} a {new.get('cores')} core")
    return changes


def device_class(hw: dict) -> str:
    return profile.classify(int(hw.get("cores") or 1), float(hw.get("ram_gb") or 0), bool(hw.get("avx2", True)))


def advice(hw: dict) -> list[str]:
    tips = []
    cls = device_class(hw)
    if cls == "low":
        tips.append("Dispositivo datato: il display passa da solo a grafica ridotta e limita i widget; per l'ascolto conviene il modello leggero.")
    elif cls == "high":
        tips.append("Hardware abbondante: puoi usare la risoluzione massima della webcam e il modello di ascolto più preciso.")
    if hw.get("ir_camera"):
        tips.append("Webcam a infrarossi: attiva il controllo anti-foto «rigido» nelle impostazioni di Visione per la massima sicurezza.")
    elif hw.get("cameras"):
        tips.append("Webcam senza infrarossi: il riconoscimento usa solo i colori e non può distinguere una foto da una persona.")
    if not hw.get("audio_in"):
        tips.append("Nessun microfono rilevato: questo dispositivo non può ascoltare.")
    if 0 < float(hw.get("ram_gb") or 0) < 2:
        tips.append("Poca memoria (meno di 2 GB): evita le funzioni pesanti su questo dispositivo.")
    return tips


def build_report(new: dict, previous: dict | None, features: list[str] | None = None, forced: bool = False) -> dict:
    return {"at": time.time(), "forced": forced, "class": device_class(new), "changes": diff(previous, new),
            "advice": advice(new), "features": features or [], "hardware": new}


def remember(history: list, report: dict) -> list:
    return ([{k: v for k, v in report.items() if k != "hardware"}] + history)[:HISTORY]


def alsa_devices(tool: str) -> list[str]:
    exe = shutil.which(tool)
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "-l"], capture_output=True, text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [m[1].strip() for m in re.finditer(r"^card \d+: [^\[]*\[([^\]]+)\]", out, re.M)][:12]


def master_hardware(hw: dict, webcam_state: dict, detected: dict, audio_in: list | None = None) -> dict:
    cameras = [f"{d['name']}" + (" (infrarossi)" if d.get("has_ir") else "") for d in webcam_state.get("devices", [])]
    return clean_hardware({"cores": hw.get("cores") or detected.get("cores"), "ram_gb": hw.get("ram_gb") or detected.get("ram_gb"),
                           "avx2": detected.get("avx2", True), "gpu": hw.get("gpu", ""), "cameras": cameras,
                           "ir_camera": any(d.get("has_ir") for d in webcam_state.get("devices", [])),
                           "arch": os.uname().machine if hasattr(os, "uname") else "", "audio_in": audio_in or [],
                           "audio_out": [],
                           "usb": [c.get("name") or f"{c['vendor']}:{c['product']}" for c in webcam_state.get("usb_video", [])]})


def read_snapshot() -> dict:
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("Hardware del server non letto: %s", exc)
        return {}


def write_snapshot(report: dict) -> None:
    try:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        tmp = SNAPSHOT.with_suffix(".tmp")
        tmp.write_text(json.dumps(report), encoding="utf-8")
        os.replace(tmp, SNAPSHOT)
    except OSError as exc:
        log.warning("Hardware del server non salvato: %s", exc)


async def run_master() -> dict:
    from feature_registry import registry as features
    from features.governor.service import governor
    from features.vision.webcams import webcams
    before = {fid: e.get("enabled") for fid, e in features.evaluate().items()}
    state = await webcams.refresh(force=True)
    governor.hardware = governor.detect()
    await features.probe_hardware()
    await features.sync()
    after = features.evaluate()
    switched = [f"{features.features[fid]['name']}: {'attivata' if e.get('enabled') else 'disattivata'}"
                for fid, e in after.items() if fid in before and before[fid] != e.get("enabled") and fid in features.features]
    mics = await asyncio.to_thread(alsa_devices, "arecord")
    hardware = master_hardware(features.hw, state, governor.hardware, mics)
    previous = read_snapshot().get("hardware")
    report = build_report(hardware, previous, switched, forced=True)
    write_snapshot(report)
    store.event("INFO", "Auto-adattamento del server: " + ("; ".join(report["changes"] + switched) or "nessun cambiamento"), "nodes")
    return report
