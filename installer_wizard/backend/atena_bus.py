import asyncio
import inspect
import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from bus_router import ENGINE, matches, new_router, valid_origin, valid_pattern, valid_topic

log = logging.getLogger("atena.bus")

SCHEMA_VERSION = "1.0"
MAX_PAYLOAD = 64 * 1024
MAX_RETAINED = 2048
DISCOVERY_TTL = 90.0


class BusError(ValueError):
    pass


@dataclass(frozen=True)
class Envelope:
    id: str
    topic: str
    ts: float
    origin: str
    schema: str
    payload: dict = field(default_factory=dict)
    retain: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class Subscription:
    def __init__(self, bus: "AtenaBus", sid: int, pattern: str, callback: Callable[[Envelope], Any]) -> None:
        self.bus, self.sid, self.pattern, self.callback = bus, sid, pattern, callback

    def cancel(self) -> None:
        self.bus._remove(self)


class AtenaBus:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._router = new_router()
        self._subs: dict[int, Subscription] = {}
        self._retained: dict[str, Envelope] = {}
        self._modules: dict[str, dict] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self.published = 0
        self.failures = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, pattern: str, callback: Callable[[Envelope], Any], replay: bool = False) -> Subscription:
        if not valid_pattern(pattern):
            raise BusError(f"invalid topic pattern: {pattern!r}")
        with self._lock:
            try:
                sid = self._router.subscribe(pattern)
            except RuntimeError as exc:
                raise BusError(str(exc)) from exc
            sub = Subscription(self, sid, pattern, callback)
            self._subs[sid] = sub
            backlog = [e for t, e in sorted(self._retained.items()) if matches(pattern, t)] if replay else []
        for envelope in backlog:
            self._deliver(sub, envelope)
        return sub

    def _remove(self, sub: Subscription) -> None:
        with self._lock:
            if self._subs.get(sub.sid) is sub:
                del self._subs[sub.sid]
                self._router.unsubscribe(sub.sid)

    def publish(self, topic: str, payload: dict | None = None, origin: str = "supervisor", retain: bool = False,
                schema: str = SCHEMA_VERSION) -> Envelope:
        if not valid_topic(topic):
            raise BusError(f"invalid topic: {topic!r}")
        if not valid_origin(origin):
            raise BusError(f"invalid origin: {origin!r}")
        body = dict(payload or {})
        if len(json.dumps(body, default=str)) > MAX_PAYLOAD:
            raise BusError("payload too large")
        envelope = Envelope(uuid.uuid4().hex, topic, self._clock(), origin, schema, body, retain)
        with self._lock:
            self.published += 1
            if retain:
                if not body:
                    self._retained.pop(topic, None)
                elif topic in self._retained or len(self._retained) < MAX_RETAINED:
                    self._retained[topic] = envelope
            targets = [self._subs[sid] for sid in self._router.route(topic)]
        for sub in targets:
            self._deliver(sub, envelope)
        return envelope

    def _deliver(self, sub: Subscription, envelope: Envelope) -> None:
        try:
            result = sub.callback(envelope)
            if inspect.isawaitable(result):
                self._schedule(result)
        except Exception as exc:
            self.failures += 1
            log.warning("subscriber of %s failed on %s: %s", sub.pattern, envelope.topic, exc)

    def _schedule(self, coroutine) -> None:
        try:
            asyncio.get_running_loop().create_task(coroutine)
        except RuntimeError:
            if self._loop is not None and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(coroutine, self._loop)
            else:
                coroutine.close()

    def retained(self, pattern: str = ">") -> list[Envelope]:
        with self._lock:
            return [e for t, e in sorted(self._retained.items()) if matches(pattern, t)]

    def announce(self, module: str, capabilities: list[str] | None = None, status: str = "ready",
                 ttl: float = DISCOVERY_TTL, info: dict | None = None) -> None:
        now = self._clock()
        with self._lock:
            known = module in self._modules
            self._modules[module] = {"module": module, "capabilities": sorted(set(capabilities or [])), "status": status,
                                     "seen": now, "ttl": ttl, "info": dict(info or {})}
            record = dict(self._modules[module])
        self.publish(f"system.discovery.{'heartbeat' if known else 'announce'}", record, origin=module)
        self.publish(f"system.module.{module}", record, origin=module, retain=True)

    def expire(self) -> list[str]:
        now = self._clock()
        with self._lock:
            lost = [m for m, r in self._modules.items() if now - r["seen"] > r["ttl"]]
            for module in lost:
                del self._modules[module]
        for module in lost:
            self.publish("system.discovery.lost", {"module": module}, origin="bus")
            self.publish(f"system.module.{module}", {}, origin="bus", retain=True)
        return lost

    def modules(self, capability: str = "") -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._modules.values() if not capability or capability in r["capabilities"]]

    def stats(self) -> dict:
        with self._lock:
            return {"engine": ENGINE, "published": self.published, "failures": self.failures,
                    "subscribers": len(self._subs), "retained": len(self._retained), "modules": len(self._modules)}

    async def run(self) -> None:
        self.bind_loop(asyncio.get_running_loop())
        while True:
            await asyncio.sleep(15)
            self.expire()


atena_bus = AtenaBus()
