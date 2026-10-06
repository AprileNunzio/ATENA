import json
import logging
import os
import re
import time
from pathlib import Path

from features.governor.profile import TIERS

log = logging.getLogger("atena.governor")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,40}$")
WIDGET_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
HISTORY = 8
BAD_P95, BAD_FPS = 80.0, 8.0
SLOW_P95, SLOW_FPS = 40.0, 14.0
GOOD_P95, GOOD_FPS = 28.0, 24.0
WORSEN_AFTER = 2
IMPROVE_AFTER = 6
MIN_GAP = 8.0
MAX_DEVICES = 200


def clamp(value, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return lo


def clean_report(body: dict) -> dict | None:
    if not isinstance(body, dict) or not ID_RE.match(str(body.get("device") or "")):
        return None
    widgets = []
    for w in (body.get("widgets") or [])[:40]:
        if isinstance(w, dict) and WIDGET_RE.match(str(w.get("id") or "")):
            widgets.append({"id": w["id"], "ms": clamp(w.get("ms"), 0, 60000), "mounts": int(clamp(w.get("mounts"), 0, 1000)),
                            "nodes": int(clamp(w.get("nodes"), 0, 100000)), "size": clamp(w.get("size"), 0, 10 ** 7)})
    return {"device": body["device"], "fps": clamp(body.get("fps"), 0, 240), "p95": clamp(body.get("p95"), 0, 5000),
            "longtask_ms": clamp(body.get("longtask_ms"), 0, 60000), "active": int(clamp(body.get("active"), 0, 100)),
            "visible": body.get("visible") is not False, "widgets": widgets}


def verdict(report: dict) -> str:
    if not report["visible"] or report["fps"] <= 0:
        return "idle"
    if report["p95"] >= BAD_P95 or report["fps"] < BAD_FPS:
        return "bad"
    if report["p95"] >= SLOW_P95 or report["fps"] < SLOW_FPS:
        return "slow"
    if report["p95"] <= GOOD_P95 and report["fps"] >= GOOD_FPS:
        return "good"
    return "ok"


def next_tier(tier: str, history: list[str]) -> str:
    index = TIERS.index(tier) if tier in TIERS else 0
    recent = history[-WORSEN_AFTER:]
    if len(recent) == WORSEN_AFTER and all(v in ("bad", "slow") for v in recent) and "bad" in recent:
        return TIERS[min(len(TIERS) - 1, index + 1)]
    if len(history) >= WORSEN_AFTER + 1 and all(v == "slow" for v in history[-(WORSEN_AFTER + 1):]):
        return TIERS[min(len(TIERS) - 1, index + 1)]
    if index > 0 and len(history) >= IMPROVE_AFTER and all(v == "good" for v in history[-IMPROVE_AFTER:]):
        return TIERS[index - 1]
    return tier


class Devices:

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, dict] = {}
        self.saved = 0.0
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log.warning("Dispositivi del display non letti: %s", exc)

    def known(self, device: str) -> dict:
        return self.data.get(device) or {"tier": None, "history": [], "last": 0.0, "fps": None, "p95": None}

    def apply(self, report: dict, base_tier: str, now: float) -> tuple[str, bool]:
        entry = self.data.setdefault(report["device"], {"tier": None, "history": [], "last": 0.0, "fps": None, "p95": None})
        if now - entry["last"] < MIN_GAP:
            return entry["tier"] or base_tier, False
        entry["last"] = now
        entry["fps"], entry["p95"], entry["active"] = report["fps"], report["p95"], report["active"]
        kind = verdict(report)
        if kind != "idle":
            entry["history"] = (entry["history"] + [kind])[-HISTORY:]
        current = entry["tier"] or base_tier
        updated = next_tier(current, entry["history"])
        if updated != current:
            entry["history"] = []
            log.info("Il display %s passa al livello grafico «%s» (p95=%.0f ms, %.0f fps)", report["device"], updated, report["p95"], report["fps"])
        entry["tier"] = updated
        if len(self.data) > MAX_DEVICES:
            for old in sorted(self.data, key=lambda k: self.data[k]["last"])[:len(self.data) - MAX_DEVICES]:
                del self.data[old]
        self.save()
        return updated, updated != current

    def forget(self, device: str | None = None) -> None:
        if device:
            self.data.pop(device, None)
        else:
            self.data.clear()
        self.save(force=True)

    def save(self, force: bool = False) -> None:
        if not force and time.time() - self.saved < 30:
            return
        self.saved = time.time()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("Dispositivi del display non salvati: %s", exc)
