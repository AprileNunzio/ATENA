import asyncio
import logging
import time
from contextlib import asynccontextmanager, contextmanager

import psutil

from config import STATE_DIR
from features.governor import conf, pressure, profile
from features.governor.devices import Devices
from features.governor.ledger import Ledger

log = logging.getLogger("atena.governor")
DEFER_STEP = 5.0
RECORD_BELOW_MS = 0.5


def read_temperature() -> float | None:
    try:
        from sysinfo import _temperature
        return _temperature()
    except (ImportError, OSError):
        return None


class Governor:

    def __init__(self) -> None:
        self.ledger = Ledger(STATE_DIR / "governor.db")
        self.devices = Devices(STATE_DIR / "governor_devices.json")
        self.pressure = pressure.Pressure()
        self.sems: dict[str, tuple[int, asyncio.Semaphore]] = {}
        self.active = {k: 0 for k in profile.JOB_KINDS}
        self.waiting = {k: 0 for k in profile.JOB_KINDS}
        self.deferred = {"count": 0, "seconds": 0.0}
        self.measuring = 0
        self.last: dict = {}
        self.cores = psutil.cpu_count() or 1
        self.hardware = self.detect()
        self.me = psutil.Process()

    def enabled(self) -> bool:
        return conf.flag("ATENA_GOVERNOR", True)

    def detect(self) -> dict:
        ram = psutil.virtual_memory().total / 1024 ** 3
        avx2 = profile.has_avx2()
        return {"cores": self.cores, "ram_gb": round(ram, 1), "avx2": avx2, "detected": profile.classify(self.cores, ram, avx2)}

    def device_class(self) -> str:
        forced = conf.choice("ATENA_GOV_CLASS", "auto", ("auto", *profile.CLASSES))
        return self.hardware["detected"] if forced == "auto" else forced

    def slots(self, kind: str) -> int:
        return profile.SLOTS[self.device_class()][kind]

    def enter_level(self) -> float:
        return conf.number("ATENA_GOV_PRESSURE_ENTER", 75.0, 30.0, 100.0)

    def leave_level(self) -> float:
        return min(self.enter_level(), conf.number("ATENA_GOV_PRESSURE_EXIT", 55.0, 10.0, 99.0))

    def sample(self) -> dict:
        mem, swap = psutil.virtual_memory(), psutil.swap_memory()
        cpu = psutil.cpu_percent(interval=None)
        load = psutil.getloadavg()[0] / self.cores if hasattr(psutil, "getloadavg") else 0.0
        raw = pressure.score(cpu, mem.percent, swap.percent, load)
        now = time.time()
        value = self.pressure.update(raw, self.enter_level(), self.leave_level(), now)
        temp = read_temperature()
        self.last = {"at": now, "cpu": cpu, "mem": mem.percent, "swap": swap.percent, "load": round(load, 2),
                     "pressure": round(value, 1), "high": self.pressure.high, "temp": temp,
                     "self_mb": round(self.me.memory_info().rss / 1048576, 1)}
        self.ledger.sample(cpu, mem.percent, swap.percent, load, value, temp)
        return self.last

    async def run(self) -> None:
        psutil.cpu_percent(interval=None)
        while True:
            try:
                if self.enabled():
                    await asyncio.to_thread(self.sample)
                    await asyncio.to_thread(self.ledger.prune, conf.number("ATENA_GOV_RETENTION_DAYS", 14.0, 1.0, 365.0))
            except Exception:
                log.exception("Campionamento delle risorse non riuscito")
            await asyncio.sleep(conf.number("ATENA_GOV_SAMPLE_S", 2.0, 1.0, 30.0))

    def busy(self, kind: str) -> bool:
        if not self.enabled() or kind in ("realtime", "interactive"):
            return False
        if kind == "maintenance":
            return self.pressure.value >= self.leave_level()
        return self.pressure.high

    async def gate(self, kind: str, name: str = "") -> float:
        if not self.busy(kind):
            return 0.0
        limit = conf.number("ATENA_GOV_DEFER_MAX_MIN", 30.0, 0.0, 1440.0) * 60
        if limit <= 0:
            return 0.0
        started = time.time()
        self.waiting[kind] += 1
        try:
            while self.busy(kind) and time.time() - started < limit:
                await asyncio.sleep(DEFER_STEP)
        finally:
            self.waiting[kind] -= 1
        waited = time.time() - started
        self.deferred["count"] += 1
        self.deferred["seconds"] += waited
        log.info("«%s» (%s) rimandato di %.0fs per il carico del sistema", name or kind, kind, waited)
        return waited

    def semaphore(self, kind: str) -> asyncio.Semaphore:
        size = self.slots(kind)
        current = self.sems.get(kind)
        if current is None or current[0] != size:
            current = (size, asyncio.Semaphore(size))
            self.sems[kind] = current
        return current[1]

    @asynccontextmanager
    async def slot(self, kind: str, name: str, size: float = 0.0):
        if not self.enabled():
            yield
            return
        await self.gate(kind, name)
        sem = self.semaphore(kind)
        self.waiting[kind] += 1
        try:
            await sem.acquire()
        finally:
            self.waiting[kind] -= 1
        self.active[kind] += 1
        try:
            with self.measure(name, kind, size):
                yield
        finally:
            self.active[kind] -= 1
            sem.release()

    @contextmanager
    def measure(self, component: str, kind: str = "job", size: float = 0.0):
        if not self.enabled():
            yield
            return
        wall0, cpu0 = time.perf_counter(), time.process_time()
        self.measuring += 1
        try:
            yield
        finally:
            shared = max(1, self.measuring)
            self.measuring -= 1
            wall = (time.perf_counter() - wall0) * 1000
            cpu = (time.process_time() - cpu0) * 1000 / shared
            if wall >= RECORD_BELOW_MS:
                self.ledger.record(component, kind, cpu, wall, size)

    def policy(self, device: str | None) -> dict:
        cls = self.device_class()
        forced_tier = conf.choice("ATENA_GOV_QUALITY", "auto", ("auto", *profile.TIERS))
        base = profile.QUALITY[cls]
        known = self.devices.known(device) if device else {}
        tier = forced_tier if forced_tier != "auto" else known.get("tier") or base
        caps = dict(profile.WIDGETS[cls])
        override = int(conf.number("ATENA_GOV_MAX_WIDGETS", 0, 0, 40))
        if override:
            caps["active"] = override
        if tier == "minimal":
            caps = {"active": max(1, caps["active"] // 2), "ambient": 0}
        return {"enabled": self.enabled(), "class": cls, "tier": tier, "max_active": caps["active"], "max_ambient": caps["ambient"],
                "report": self.enabled() and conf.flag("ATENA_GOV_CLIENT_REPORT", True), "report_every_s": 30,
                "server_busy": self.pressure.high}

    def report(self, clean: dict) -> dict:
        base = profile.QUALITY[self.device_class()]
        _, changed = self.devices.apply(clean, base, time.time())
        for w in clean["widgets"]:
            self.ledger.record(f"widget:{w['id']}", "widget", w["ms"], w["ms"], w["nodes"])
        return {**self.policy(clean["device"]), "changed": changed}

    def state(self, minutes: int = 60) -> dict:
        return {"enabled": self.enabled(), "hardware": self.hardware, "class": self.device_class(), "now": self.last,
                "thresholds": {"enter": self.enter_level(), "leave": self.leave_level()},
                "slots": {k: {"max": self.slots(k), "active": self.active[k], "waiting": self.waiting[k]} for k in profile.JOB_KINDS},
                "deferred": {"count": self.deferred["count"], "seconds": round(self.deferred["seconds"], 1)},
                "top": self.ledger.top(minutes), "policy": self.policy(None),
                "devices": [{"device": k[:8] + "…", "tier": v.get("tier"), "fps": v.get("fps"), "p95": v.get("p95"),
                             "seen_s": int(time.time() - v.get("last", 0))} for k, v in self.devices.data.items()]}


governor = Governor()
