import asyncio
import logging
import time

from config import env_get
from state import store

from features.ducking import targets

log = logging.getLogger("atena.ducking")

BEAT_TIMEOUT = 15
RELEASE_AFTER = 3
TOLERANCE = 0.03


def enabled() -> bool:
    return env_get("ATENA_DUCKING", "1") != "0"


def level() -> float:
    try:
        return max(0.05, min(0.8, int(env_get("ATENA_DUCK_LEVEL", "25")) / 100))
    except ValueError:
        return 0.25


def include_home() -> bool:
    return env_get("ATENA_DUCK_HOME", "1") != "0"


class Ducker:
    def __init__(self) -> None:
        self.ducked: list[targets.Target] = []
        self.active = False
        self.beat = 0.0
        self.off_at = 0.0
        self.lock = asyncio.Lock()

    async def collect(self) -> list[targets.Target]:
        found = targets.music()
        found += await targets.spotify_target()
        if include_home():
            found += await targets.tv({t.ident for t in found})
            found += targets.home()
        return found

    async def duck(self) -> None:
        async with self.lock:
            if self.active:
                return
            self.active = True
            factor, done = level(), []
            for target in await self.collect():
                target.ducked = round(target.original * factor, 2)
                if await targets.attempt(target.set(target.ducked), target.name):
                    done.append(target)
            self.ducked = done
            if done:
                store.event("INFO", f"Volume abbassato per la conversazione: {', '.join(t.name for t in done)}", "ducking")

    async def release(self) -> None:
        async with self.lock:
            if not self.active:
                return
            self.active = False
            restored = []
            for target in self.ducked:
                now = await targets.probe(target.current(), target.name)
                if now is not None and abs(now - target.ducked) > TOLERANCE:
                    continue
                if await targets.attempt(target.set(target.original), target.name):
                    restored.append(target.name)
            self.ducked = []
            if restored:
                store.event("INFO", f"Volume ripristinato: {', '.join(restored)}", "ducking")

    async def signal(self, on: bool) -> None:
        now = time.time()
        if on:
            self.beat, self.off_at = now, 0.0
            if enabled():
                await self.duck()
        elif self.active and not self.off_at:
            self.off_at = now

    async def tick(self) -> None:
        now = time.time()
        if not self.active:
            return
        if (self.off_at and now - self.off_at >= RELEASE_AFTER) or now - self.beat > BEAT_TIMEOUT or not enabled():
            self.off_at = 0.0
            await self.release()

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Ripristino del volume dopo la conversazione")
            await asyncio.sleep(1)


ducker = Ducker()
