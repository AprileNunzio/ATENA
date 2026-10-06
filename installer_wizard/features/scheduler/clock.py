import asyncio
import logging
import time
from datetime import datetime, timedelta

from features.automations import sun
from features.automations.expr import number
from features.scheduler import cronexpr, misfire
from features.scheduler.marks import Marks

log = logging.getLogger("atena.scheduler")
CLOCK_KINDS = ("time", "interval", "cron", "sun")
CATCH_UP_KINDS = ("time", "cron")


class Policy:

    def __init__(self, env) -> None:
        self.env = env

    def misfire(self, trigger: dict) -> str:
        return misfire.policy_of(trigger.get("misfire"), misfire.policy_of(self.env("ATENA_SCHED_MISFIRE", "run_once"), "run_once"))

    def grace(self) -> float:
        return self._num("ATENA_SCHED_GRACE_MIN", 120.0, 0.0, 10080.0) * 60

    def max_runs(self) -> int:
        return int(self._num("ATENA_SCHED_MAX_CATCHUP", 3.0, 1.0, 50.0))

    def jitter(self) -> float:
        return self._num("ATENA_SCHED_JITTER_S", 0.0, 0.0, 300.0)

    def enabled(self) -> bool:
        return self.env("ATENA_SCHED_PERSIST", "1") != "0"

    def _num(self, key: str, default: float, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(self.env(key, str(default)))))
        except ValueError:
            return default


def spec_of(t: dict) -> cronexpr.Cron | None:
    try:
        if t["type"] == "cron":
            return cronexpr.parse(t.get("expr"))
        at = str(t.get("at") or "")
        hour, _, minute = at.partition(":")
        return cronexpr.build(int(minute), int(hour), t.get("days") or None)
    except (cronexpr.CronError, ValueError, KeyError):
        return None


class TriggerClock:

    def __init__(self, marks: Marks, start, env) -> None:
        self.marks = marks
        self.start = start
        self.policy = Policy(env)
        self.stamps: dict[str, str] = {}
        self.caught_up = False
        self.cron_cache: dict[str, cronexpr.Cron | None] = {}

    def _cron(self, expr: str) -> cronexpr.Cron | None:
        if expr not in self.cron_cache:
            try:
                self.cron_cache[expr] = cronexpr.parse(expr)
            except cronexpr.CronError as exc:
                log.warning("Espressione cron «%s» non valida: %s", expr, exc)
                self.cron_cache[expr] = None
        return self.cron_cache[expr]

    def _fire(self, a: dict, t: dict, key: str, label: str, at: float) -> None:
        self.marks.set(key, at, now_flush=True)
        trigger = {**t, "label": label}
        delay = misfire.jitter(self.policy.jitter())
        if delay:
            asyncio.get_event_loop().call_later(delay, self.start, a, trigger)
        else:
            self.start(a, trigger)

    def tick(self, automations: list[dict], now: datetime | None = None) -> None:
        now = now or datetime.now()
        stamp, ts = now.strftime("%Y-%m-%d %H:%M"), time.time()
        self.marks.persist = self.policy.enabled()
        if not self.caught_up:
            if self.marks.persist:
                self.catch_up(automations, now)
            self.caught_up = True
        for a in automations:
            if not a.get("enabled", True):
                continue
            for t in a.get("triggers") or []:
                kind = t["type"]
                if kind not in CLOCK_KINDS:
                    continue
                key = f"{a['id']}:{t['id']}"
                if self.marks.get(key) is None:
                    self.marks.set(key, ts)
                if kind in ("time", "cron"):
                    spec = spec_of(t) if kind == "time" else self._cron(str(t.get("expr") or ""))
                    if spec and spec.matches(now) and self.stamps.get(key) != stamp:
                        self.stamps[key] = stamp
                        self._fire(a, t, key, f"ore {now.strftime('%H:%M')}" if kind == "time" else f"cron {spec.text}", ts)
                elif kind == "interval":
                    self._interval(a, t, key, ts)
                else:
                    self._sun(a, t, key, now, stamp, ts)
        self.marks.flush()

    def _interval(self, a: dict, t: dict, key: str, ts: float) -> None:
        every = max(1.0, number(t.get("minutes"), 60)) * 60
        verdict = misfire.interval_overdue(self.marks.get(key) or ts, every, ts, self.policy.misfire(t), self.policy.grace())
        if verdict == "reset":
            self.marks.set(key, ts)
        elif verdict == "run":
            self._fire(a, t, key, f"ogni {int(every / 60)} minuti", ts)

    def _sun(self, a: dict, t: dict, key: str, now: datetime, stamp: str, ts: float) -> None:
        target = sun.times(now.date()).get(t.get("event") or "sunset")
        if not target:
            return
        moment = (target + timedelta(minutes=number(t.get("offset"), 0))).strftime("%Y-%m-%d %H:%M")
        if moment == stamp and self.stamps.get(key) != stamp:
            self.stamps[key] = stamp
            self._fire(a, t, key, "alba" if t.get("event") == "sunrise" else "tramonto", ts)

    def catch_up(self, automations: list[dict], now: datetime) -> int:
        self.caught_up = True
        started = 0
        valid = set()
        for a in automations:
            for t in a.get("triggers") or []:
                key = f"{a['id']}:{t['id']}"
                valid.add(key)
                last = self.marks.get(key)
                if not a.get("enabled", True) or t["type"] not in CATCH_UP_KINDS or last is None:
                    continue
                spec = spec_of(t) if t["type"] == "time" else self._cron(str(t.get("expr") or ""))
                if not spec:
                    continue
                since = max(datetime.fromtimestamp(last), now - timedelta(seconds=self.policy.grace()))
                missed = cronexpr.fires_between(spec, since, now - timedelta(minutes=1))
                for moment in misfire.plan(missed, self.policy.misfire(t), self.policy.grace(), now, self.policy.max_runs()):
                    self.stamps[key] = now.strftime("%Y-%m-%d %H:%M")
                    self._fire(a, t, key, f"recupero: scattata alle {moment.strftime('%H:%M del %d/%m')} mentre ero spento", time.time())
                    started += 1
        self.marks.prune(valid | {k for k in self.marks.data if k.startswith("_")})
        if started:
            log.info("Recuperate %d esecuzioni mancate durante lo spegnimento", started)
        return started

    def upcoming(self, automations: list[dict], now: datetime | None = None, limit: int = 20) -> list[dict]:
        now = now or datetime.now()
        rows = []
        for a in automations:
            if not a.get("enabled", True):
                continue
            for t in a.get("triggers") or []:
                if t["type"] in ("time", "cron"):
                    spec = spec_of(t) if t["type"] == "time" else self._cron(str(t.get("expr") or ""))
                    if spec:
                        try:
                            rows.append({"automation": a["name"], "id": a["id"], "next": cronexpr.next_after(spec, now).isoformat(timespec="minutes")})
                        except cronexpr.CronError:
                            continue
                elif t["type"] == "interval":
                    last = self.marks.get(f"{a['id']}:{t['id']}") or time.time()
                    at = datetime.fromtimestamp(last + max(1.0, number(t.get("minutes"), 60)) * 60)
                    rows.append({"automation": a["name"], "id": a["id"], "next": max(at, now).isoformat(timespec="minutes")})
        return sorted(rows, key=lambda r: r["next"])[:limit]
