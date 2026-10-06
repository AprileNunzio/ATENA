import json
import logging
import os
import time
from pathlib import Path

import earconf

log = logging.getLogger("atena.ear")

TUNING_FILE = Path(os.environ.get("ATENA_EAR_TUNING", "/var/lib/atena/ear_tuning.json"))
THRESHOLD_MIN, THRESHOLD_MAX = 0.25, 0.80
WAKE_GAIN_MIN, WAKE_GAIN_MAX = 1.0, 30.0
MAX_GAIN_MIN, MAX_GAIN_MAX = 2.0, 80.0
STEP = 0.05
WINDOW_CHUNKS = 6
MIN_EVENTS = 3
HISTORY = 40
FRESH = {"chunks": 0, "missed": 0, "false_instant": 0, "true_wakes": 0, "weak": 0, "clipped": 0}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def decide(window: dict, state: dict) -> list[tuple[str, float, str]]:
    changes = []
    missed, false_hits, weak, clipped = window["missed"], window["false_instant"], window["weak"], window["clipped"]
    chunks = max(1, window["chunks"])
    threshold = state["wake_threshold"]
    if missed >= 2 and missed > false_hits and threshold > THRESHOLD_MIN:
        changes.append(("wake_threshold", clamp(threshold - STEP, THRESHOLD_MIN, THRESHOLD_MAX),
                        f"{missed} attivazioni mancate nelle ultime registrazioni"))
    elif false_hits >= 2 and false_hits > missed and threshold < THRESHOLD_MAX:
        changes.append(("wake_threshold", clamp(threshold + STEP, THRESHOLD_MIN, THRESHOLD_MAX),
                        f"{false_hits} attivazioni a vuoto nelle ultime registrazioni"))
    if weak / chunks >= 0.5 and clipped / chunks < 0.1:
        changes.append(("wake_gain", clamp(state["wake_gain"] + 0.5, WAKE_GAIN_MIN, WAKE_GAIN_MAX),
                        "voce spesso debole: amplifico di più l'ascolto"))
        changes.append(("max_gain", clamp(state["max_gain"] + 5, MAX_GAIN_MIN, MAX_GAIN_MAX),
                        "voce spesso debole: alzo l'amplificazione massima"))
    elif clipped / chunks >= 0.25 and state["wake_gain"] > WAKE_GAIN_MIN:
        changes.append(("wake_gain", clamp(state["wake_gain"] - 0.5, WAKE_GAIN_MIN, WAKE_GAIN_MAX),
                        "voce spesso troppo forte: riduco l'amplificazione"))
    return changes


class Tuning:

    def __init__(self) -> None:
        self.state = {"wake_threshold": None, "wake_gain": 1.0, "max_gain": None, "history": [], "window": dict(FRESH)}
        self.mtime = 0.0
        self.load()

    def load(self) -> None:
        try:
            stat = TUNING_FILE.stat()
            if stat.st_mtime == self.mtime:
                return
            self.state.update(json.loads(TUNING_FILE.read_text(encoding="utf-8")))
            self.mtime = stat.st_mtime
        except FileNotFoundError:
            if self.mtime:
                self.state = {"wake_threshold": None, "wake_gain": 1.0, "max_gain": None, "history": [], "window": dict(FRESH)}
                self.mtime = 0.0
        except (OSError, ValueError) as exc:
            log.warning("Regolazioni dell'ascolto non lette: %s", exc)

    def save(self) -> None:
        try:
            TUNING_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = TUNING_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, TUNING_FILE)
            self.mtime = TUNING_FILE.stat().st_mtime
        except OSError as exc:
            log.warning("Regolazioni dell'ascolto non salvate: %s", exc)

    def wake_threshold(self) -> float:
        base = earconf.number("ATENA_WAKEWORD_THRESHOLD", 0.5, THRESHOLD_MIN, THRESHOLD_MAX)
        if not earconf.flag("ATENA_EAR_AUTOTUNE", True) or self.state.get("wake_threshold") is None:
            return base
        return clamp(float(self.state["wake_threshold"]), THRESHOLD_MIN, THRESHOLD_MAX)

    def wake_gain_limit(self) -> float:
        base = earconf.number("ATENA_EAR_WAKE_GAIN", 8.0, WAKE_GAIN_MIN, WAKE_GAIN_MAX)
        if not earconf.flag("ATENA_EAR_AUTOTUNE", True):
            return base
        return clamp(base * float(self.state.get("wake_gain") or 1.0), WAKE_GAIN_MIN, WAKE_GAIN_MAX)

    def max_gain(self) -> float:
        base = earconf.number("ATENA_EAR_MAX_GAIN", 30.0, MAX_GAIN_MIN, MAX_GAIN_MAX)
        if not earconf.flag("ATENA_EAR_AUTOTUNE", True) or self.state.get("max_gain") is None:
            return base
        return clamp(float(self.state["max_gain"]), MAX_GAIN_MIN, MAX_GAIN_MAX)

    def observe(self, review: dict) -> list[dict]:
        window = self.state["window"]
        window["chunks"] += 1
        for key in ("missed", "false_instant", "true_wakes"):
            window[key] += int(review.get(key, 0))
        window["weak"] += 1 if review.get("weak") else 0
        window["clipped"] += 1 if review.get("clipped") else 0
        applied = []
        if window["chunks"] >= WINDOW_CHUNKS and window["missed"] + window["false_instant"] + window["weak"] >= MIN_EVENTS:
            if earconf.flag("ATENA_EAR_AUTOTUNE", True):
                current = {"wake_threshold": self.wake_threshold(), "wake_gain": float(self.state.get("wake_gain") or 1.0),
                           "max_gain": self.max_gain()}
                for key, value, why in decide(window, current):
                    self.state[key] = round(value, 3)
                    entry = {"at": time.time(), "key": key, "value": round(value, 3), "why": why}
                    self.state["history"] = (self.state["history"] + [entry])[-HISTORY:]
                    applied.append(entry)
                    log.info("Regolazione automatica dell'ascolto: %s = %.2f (%s)", key, value, why)
            self.state["window"] = dict(FRESH)
        self.save()
        return applied

    def snapshot(self) -> dict:
        return {"wake_threshold": round(self.wake_threshold(), 3), "wake_gain_limit": round(self.wake_gain_limit(), 2),
                "max_gain": round(self.max_gain(), 1), "history": self.state.get("history", [])[-10:],
                "window": self.state.get("window", dict(FRESH)), "autotune": earconf.flag("ATENA_EAR_AUTOTUNE", True)}


tuning = Tuning()
