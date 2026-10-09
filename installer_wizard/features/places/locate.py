import math
import threading
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass

from features.places.store import Room, store

HALF_LIFE = {"voice": 45.0, "face": 90.0, "request": 20.0}
WEIGHT = {"voice": 1.0, "face": 0.9, "request": 0.7}
MIN_SCORE = 0.25
KEEP = 120.0

current_room: ContextVar[Room | None] = ContextVar("atena_room", default=None)


@dataclass(frozen=True)
class Clue:
    kind: str
    key: str
    strength: float
    at: float


class Locator:

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.clues: dict[str, deque[Clue]] = defaultdict(lambda: deque(maxlen=64))

    def note(self, who: str, kind: str, key: str, strength: float = 1.0, at: float | None = None) -> None:
        if not who or kind not in WEIGHT or not key:
            return
        with self.lock:
            self.clues[who].append(Clue(kind, key, max(0.0, min(float(strength), 1.0)), at or time.time()))

    def scores(self, who: str, now: float | None = None) -> dict[str, float]:
        now = now or time.time()
        totals: dict[str, float] = defaultdict(float)
        with self.lock:
            clues = [c for c in self.clues.get(who, ()) if now - c.at <= KEEP]
        for clue in clues:
            room = store.room_of(clue.key)
            if room is None:
                continue
            decay = math.pow(0.5, (now - clue.at) / HALF_LIFE[clue.kind])
            totals[room.id] += WEIGHT[clue.kind] * clue.strength * decay
        return dict(totals)

    def room(self, who: str, now: float | None = None) -> Room | None:
        totals = self.scores(who, now)
        if not totals:
            return None
        best = max(totals, key=totals.get)
        if totals[best] < MIN_SCORE:
            return None
        return store.rooms.get(best)

    def resolve(self, who: str, request_key: str = "") -> Room | None:
        if request_key:
            self.note(who or f"device:{request_key}", "request", request_key)
        return (self.room(who) if who else None) or store.room_of(request_key)

    def everyone(self) -> dict[str, dict]:
        with self.lock:
            people = [w for w in self.clues if not w.startswith("device:")]
        out = {}
        for who in people:
            room = self.room(who)
            if room:
                out[who] = {"room_id": room.id, "room": room.name}
        return out


locator = Locator()
