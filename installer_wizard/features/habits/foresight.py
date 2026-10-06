import threading
import time
from collections import defaultdict
from datetime import datetime

from features.habits.miner import FOLLOW_UP, WINDOW_DAYS, service_for
from features.home_assistant.nlu.text import norm, phrase_stems, stem

ARRIVAL_TTL = 15 * 60
WINDOW_TTL = 10 * 60
TIME_SPAN = 30
MIN_SUPPORT = 3
MIN_CONFIDENCE = 0.5
MAX_ARMED = 12
NEVER_ARMED = {("lock", "unlocked"), ("cover", "open"), ("alarm_control_panel", "disarmed")}
VERBS = {
    "on": {"accend", "attiv"}, "off": {"spegn", "disattiv", "togl"},
    "open": {"apr", "alz"}, "closed": {"chiud", "abbass"}, "locked": {"chiud", "blocc"},
    "playing": {"riproduc", "suon", "mett", "play", "avvi"}, "paused": {"paus", "ferm"},
    "idle": {"ferm", "stop"}, "heat": {"riscald", "accend"}, "cool": {"raffresc", "accend"},
}


def _verbs(state: str) -> set[str]:
    return VERBS.get(state, set())


def _arrival_predictions(rows: list[tuple]) -> list[tuple[str, str, float]]:
    arrivals = [r[0] for r in rows if r[7] == "arrival"]
    if len(arrivals) < MIN_SUPPORT:
        return []
    actions = [(r[0], r[1], r[2]) for r in rows if r[7] == "action"]
    follow: dict[tuple, int] = defaultdict(int)
    for at in arrivals:
        seen = {(e, s) for t, e, s in actions if 0 <= t - at <= FOLLOW_UP}
        for key in seen:
            follow[key] += 1
    return [(e, s, round(n / len(arrivals), 2)) for (e, s), n in follow.items()
            if n >= MIN_SUPPORT and n / len(arrivals) >= MIN_CONFIDENCE]


def _window_predictions(rows: list[tuple], now: float) -> list[tuple[str, str, float]]:
    current = datetime.fromtimestamp(now)
    minute, weekend = current.hour * 60 + current.minute, current.weekday() >= 5
    days: set = set()
    hits: dict[tuple, set] = defaultdict(set)
    for at, entity, state, wd, mins, _, _, kind in rows:
        if (wd >= 5) != weekend:
            continue
        day = datetime.fromtimestamp(at).date()
        days.add(day)
        gap = min(abs(mins - minute), 1440 - abs(mins - minute))
        if kind == "action" and gap <= TIME_SPAN:
            hits[(entity, state)].add(day)
    if not days:
        return []
    return [(e, s, round(len(d) / len(days), 2)) for (e, s), d in hits.items()
            if len(d) >= MIN_SUPPORT and len(d) / len(days) >= MIN_CONFIDENCE]


def predict(rows: list[tuple], now: float, arrival: bool) -> list[tuple[str, str, float, str]]:
    rows = [r for r in rows if r[0] >= now - WINDOW_DAYS * 86400]
    out: dict[tuple, tuple] = {}
    for entity, state, confidence in _window_predictions(rows, now):
        out[(entity, state)] = (entity, state, confidence, "orario")
    if arrival:
        for entity, state, confidence in _arrival_predictions(rows):
            if confidence > out.get((entity, state), ("", "", 0.0))[2]:
                out[(entity, state)] = (entity, state, confidence, "arrivo")
    allowed = [p for p in out.values() if (p[0].split(".")[0], p[1]) not in NEVER_ARMED and service_for(p[0], p[1])]
    return sorted(allowed, key=lambda p: -p[2])[:MAX_ARMED]


def plan_for(entity: str, state: str) -> dict:
    service, data = service_for(entity, state)
    domain, name = service.split(".", 1)
    return {"kind": "command", "action": "foresight", "calls": [{"domain": domain, "service": name, "entity_ids": [entity],
            "data": data}], "entities": [entity], "sensitive": False, "how": "previsione", "origin": {"kind": "foresight", "id": ""}}


def _feedback():
    try:
        from features.habits.feedback import feedback
        return feedback
    except Exception:
        return None


class Foresight:
    def __init__(self, clock=time.time, judge=None) -> None:
        self.clock = clock
        self.judge = judge
        self.lock = threading.Lock()
        self.armed: dict[tuple, dict] = {}
        self.hits = 0

    def arm(self, rows: list[tuple], names: dict, arrival: bool = False) -> list[dict]:
        now = self.clock()
        ttl = ARRIVAL_TTL if arrival else WINDOW_TTL
        fresh = {}
        judge = self.judge or _feedback()
        for entity, state, confidence, reason in predict(rows, now, arrival):
            if judge is not None:
                if judge.suppressed("foresight", "", entity, state):
                    continue
                confidence = round(confidence * judge.acceptance("foresight", "", entity, state), 2)
            label = names.get(entity) or entity.split(".", 1)[-1].replace("_", " ")
            fresh[(entity, state)] = {"entity": entity, "state": state, "confidence": confidence, "reason": reason,
                                      "until": now + ttl, "stems": set(phrase_stems(label)), "plan": plan_for(entity, state)}
        with self.lock:
            self._expire(now)
            for key, item in fresh.items():
                old = self.armed.get(key)
                if not old or old["until"] < item["until"]:
                    self.armed[key] = item
            return [dict(item, stems=sorted(item["stems"])) for item in self.armed.values()]

    def _expire(self, now: float) -> None:
        for key in [k for k, v in self.armed.items() if v["until"] < now]:
            del self.armed[key]

    def match(self, text: str) -> dict | None:
        words = {stem(w) for w in norm(text).split()}
        with self.lock:
            self._expire(self.clock())
            candidates = [item for item in self.armed.values()
                          if words & _verbs(item["state"]) and item["stems"] and item["stems"] <= words]
        if len(candidates) != 1:
            return None
        self.hits += 1
        return candidates[0]["plan"]

    def listing(self) -> list[dict]:
        with self.lock:
            self._expire(self.clock())
            return [{k: v for k, v in item.items() if k not in ("stems", "plan")} for item in self.armed.values()]


foresight = Foresight()
