import json
import logging
import os
import threading
import time
from datetime import datetime

from config import STATE_DIR

from features.twin.model import predicted_state

log = logging.getLogger("atena.feedback")
FILE = STATE_DIR / "feedback.json"
WINDOW = 180.0
SETTLE = 3.0
MIN_UNDO = 2
SUPPRESS_BELOW = 0.4
FORGET_LEARNED_AFTER = 2
MAX_KEYS = 2000
SOURCE_KIND = {"automazione": "automation", "previsione": "foresight", "memoria": "learned", "cervello": "llm",
               "regole": "rules", "conferma": "confirm", "voce": "voice"}
AUTONOMOUS = {"automation", "foresight", "learned", "llm"}


def context(now: float, people: int, sun_up: bool) -> str:
    moment = datetime.fromtimestamp(now)
    day = "weekend" if moment.weekday() >= 5 else "weekday"
    return f"{day}|{moment.hour // 3}|{'day' if sun_up else 'dark'}|{'occupied' if people else 'empty'}"


def _kind(plan: dict, source: str) -> tuple[str, str]:
    origin = plan.get("origin") if isinstance(plan.get("origin"), dict) else {}
    if origin.get("kind"):
        return str(origin["kind"]), str(origin.get("id") or "")
    if plan.get("action") == "foresight":
        return "foresight", ""
    return SOURCE_KIND.get(str(source).split(" ")[0], "voice"), ""


class Feedback:
    def __init__(self, clock=time.time, environment=None) -> None:
        self.clock = clock
        self.environment = environment or self._environment
        self.lock = threading.Lock()
        self.pending: list[dict] = []
        self.data = self._load()
        self.dirty = False

    @staticmethod
    def _environment() -> tuple[int, bool]:
        try:
            from features.automations import sun
            from features.automations.bus import bus
            return len(bus.present), bool(sun.up())
        except Exception:
            return 1, True

    @staticmethod
    def _load() -> dict:
        try:
            data = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return {"stats": data.get("stats", {}) if isinstance(data.get("stats"), dict) else {},
                "texts": data.get("texts", {}) if isinstance(data.get("texts"), dict) else {}}

    def save(self) -> None:
        with self.lock:
            if not self.dirty:
                return
            payload = json.dumps(self.data, ensure_ascii=False)
            self.dirty = False
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, FILE)

    def context_now(self) -> str:
        people, sun_up = self.environment()
        return context(self.clock(), people, sun_up)

    @staticmethod
    def key(kind: str, origin: str, entity: str, target: str, ctx: str) -> str:
        return "§".join((kind, origin, entity, target, ctx))

    def observe(self, plan: dict, text: str, source: str, before: dict) -> int:
        kind, origin = _kind(plan, source)
        now, ctx = self.clock(), self.context_now()
        added = 0
        with self.lock:
            for call in plan.get("calls", []):
                for eid in call.get("entity_ids") or []:
                    after = predicted_state(eid, call["service"], call.get("data") or {}, before.get(eid))
                    if after is None or after == before.get(eid):
                        continue
                    self.pending = [p for p in self.pending if p["entity"] != eid]
                    self.pending.append({"entity": eid, "before": before.get(eid), "after": after, "kind": kind, "origin": origin,
                                         "at": now, "ctx": ctx, "text": text[:200], "applied": False})
                    added += 1
        return added

    def superseded(self, entity_ids: list[str]) -> None:
        wanted = set(entity_ids)
        with self.lock:
            self.pending = [p for p in self.pending if p["entity"] not in wanted]

    def on_event(self, ev: dict) -> None:
        if ev.get("name") != "state_changed":
            return
        data = ev.get("data") or {}
        eid, new = str(data.get("entity_id", "")), data.get("to")
        if not eid or new in (None, "unavailable", "unknown"):
            return
        now = self.clock()
        with self.lock:
            match = next((p for p in self.pending if p["entity"] == eid), None)
            if match is None:
                return
            if new == match["after"]:
                match["applied"] = True
                return
            if not match["applied"] and now - match["at"] < SETTLE:
                return
            self.pending.remove(match)
        self._settle(match, undone=True)

    def sweep(self) -> int:
        now = self.clock()
        with self.lock:
            done = [p for p in self.pending if now - p["at"] >= WINDOW]
            self.pending = [p for p in self.pending if now - p["at"] < WINDOW]
        for p in done:
            self._settle(p, undone=False)
        self.save()
        return len(done)

    def _settle(self, p: dict, undone: bool) -> None:
        key = self.key(p["kind"], p["origin"], p["entity"], p["after"], p["ctx"])
        with self.lock:
            stats = self.data["stats"]
            if key not in stats and len(stats) >= MAX_KEYS:
                oldest = min(stats, key=lambda k: stats[k]["last"])
                del stats[oldest]
            row = stats.setdefault(key, {"ok": 0, "undo": 0, "last": 0.0})
            row["undo" if undone else "ok"] += 1
            row["last"] = self.clock()
            forget = False
            if undone and p["kind"] in ("learned", "llm") and p["text"]:
                count = self.data["texts"].get(p["text"], 0) + 1
                self.data["texts"][p["text"]] = count
                forget = count >= FORGET_LEARNED_AFTER
            self.dirty = True
        if undone:
            self._publish("feedback.undo", {"entity": p["entity"], "kind": p["kind"], "origin": p["origin"], "target": p["after"],
                                            "context": p["ctx"], "acceptance": self.acceptance_of(key)[0]})
        if forget:
            self._forget_learned(p["text"])

    def acceptance_of(self, key: str) -> tuple[float, int]:
        row = self.data["stats"].get(key)
        if not row:
            return 1.0, 0
        n = row["ok"] + row["undo"]
        return (row["ok"] + 1) / (n + 2), n

    def acceptance(self, kind: str, origin: str, entity: str, target: str, ctx: str | None = None) -> float:
        return self.acceptance_of(self.key(kind, origin, entity, target, ctx or self.context_now()))[0]

    def suppressed(self, kind: str, origin: str, entity: str, target: str, ctx: str | None = None) -> bool:
        if kind not in AUTONOMOUS:
            return False
        key = self.key(kind, origin, entity, target, ctx or self.context_now())
        row = self.data["stats"].get(key)
        if not row or row["undo"] < MIN_UNDO:
            return False
        blocked = self.acceptance_of(key)[0] < SUPPRESS_BELOW
        if blocked:
            self._publish("feedback.suppressed", {"entity": entity, "kind": kind, "origin": origin, "target": target, "context": key.split("§")[-1]})
        return blocked

    def _forget_learned(self, text: str) -> None:
        try:
            from features.home_assistant.home import brain
            from features.home_assistant.nlu.text import norm
            key = norm(text)
            if brain.learned.pop(key, None) is not None:
                brain.db.run(lambda c: c.execute("DELETE FROM learned WHERE text = ?", (key,)))
                log.info("Apprendimento implicito: dimenticato il piano appreso per «%s»", text[:80])
                self._publish("feedback.forgotten", {"text": text[:200]})
        except Exception as exc:
            log.debug("Piano appreso non dimenticato: %s", exc)

    @staticmethod
    def _publish(topic: str, payload: dict) -> None:
        try:
            from atena_bus import BusError, atena_bus
            atena_bus.publish(topic, payload, origin="feedback")
        except (ImportError, BusError):
            pass

    def listing(self) -> list[dict]:
        out = []
        with self.lock:
            items = list(self.data["stats"].items())
        for key, row in items:
            kind, origin, entity, target, ctx = key.split("§")
            mean, n = self.acceptance_of(key)
            out.append({"key": key, "kind": kind, "origin": origin, "entity": entity, "target": target, "context": ctx,
                        "ok": row["ok"], "undo": row["undo"], "acceptance": round(mean, 2), "samples": n, "last": row["last"],
                        "suppressed": kind in AUTONOMOUS and row["undo"] >= MIN_UNDO and mean < SUPPRESS_BELOW})
        return sorted(out, key=lambda r: (r["acceptance"], -r["last"]))

    def reset(self, key: str = "") -> int:
        with self.lock:
            if key:
                removed = 1 if self.data["stats"].pop(key, None) is not None else 0
            else:
                removed = len(self.data["stats"])
                self.data = {"stats": {}, "texts": {}}
            self.dirty = True
        self.save()
        return removed


feedback = Feedback()
