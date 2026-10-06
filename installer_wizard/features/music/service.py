import asyncio
import logging
import time

from features.governor.service import governor
from features.music import conf, covers, enrich, identify, legacy, listening, lyrics_store, organizer, renamer, scanner, sharing
from state import store

log = logging.getLogger("atena.music")
FIRST_DELAY = 20.0
COVER_EVERY = 3600.0
WATCH_EVERY = 8.0
ONLINE_GAP = 45.0
IDENTIFY_BATCH = 3
IDENTIFY_FILES = 8
RENAME_BATCH = 60
state = {"cycles": 0, "last": 0.0, "organized": {}, "covers": 0, "covers_at": 0.0, "enriched": 0, "lyrics": 0, "identified": 0, "renamed": 0}


class LibraryService:

    def __init__(self) -> None:
        self.wake = asyncio.Event()
        self.full_next = False
        self.lock = asyncio.Lock()

    def trigger(self, full: bool = False) -> None:
        self.full_next = self.full_next or full
        self.wake.set()

    async def cycle(self, manual: bool = False) -> dict:
        async with self.lock:
            full, self.full_next = self.full_next, False
            moved = {}
            if manual or conf.organize():
                moved = await asyncio.to_thread(organizer.sweep, manual)
                if moved.get("unassigned") and conf.identify():
                    held = [p for p in organizer.held if p.exists()]
                    if await identify.inbox(held, conf.write_tags(), IDENTIFY_FILES if manual else IDENTIFY_BATCH):
                        for path in held:
                            organizer.held.pop(path, None)
                        again = await asyncio.to_thread(organizer.sweep, manual)
                        moved = {k: moved.get(k, 0) + again.get(k, 0) if k != "unassigned" else again.get(k, 0) for k in set(moved) | set(again)}
                state["organized"] = moved
                for item in organizer.progress["moves"][:moved["moved"]]:
                    store.event("INFO", f"Musica smistata: {item['from']} → {item['to']}", "music")
            if manual:
                await asyncio.to_thread(scanner.scan, full)
            else:
                async with governor.slot("maintenance", "musica-libreria"):
                    await asyncio.to_thread(scanner.scan, full)
            fresh = bool(scanner.progress["added"]) or manual
            if time.time() - state["covers_at"] > (ONLINE_GAP if fresh else COVER_EVERY):
                state["covers_at"] = time.time()
                await self.online()
            if conf.rename():
                state["renamed"] += (await asyncio.to_thread(renamer.run, RENAME_BATCH))["renamed"]
            await asyncio.to_thread(listening.prune)
            await asyncio.to_thread(sharing.purge)
            state["cycles"] += 1
            state["last"] = time.time()
            return {"sorted": moved, "scan": dict(scanner.progress), "errors": list(organizer.progress["errors"])}

    async def online(self) -> None:
        try:
            if conf.identify():
                found = await identify.run(IDENTIFY_BATCH, conf.write_tags())
                state["identified"] += found["identified"]
            if conf.covers_online():
                state["enriched"] += await enrich.run()
                state["covers"] += await covers.complete()
            if conf.lyrics_online():
                state["lyrics"] += await lyrics_store.fetch_missing()
        except Exception as exc:
            log.warning("Ricerca online di copertine e testi non riuscita: %s", exc)

    async def run_now(self, full: bool = False) -> dict:
        self.full_next = self.full_next or full
        return await self.cycle(True)

    async def idle(self) -> None:
        deadline = time.time() + conf.scan_minutes() * 60
        while time.time() < deadline:
            try:
                await asyncio.wait_for(self.wake.wait(), WATCH_EVERY)
                return
            except asyncio.TimeoutError:
                if conf.organize() and await asyncio.to_thread(organizer.pending):
                    return

    async def run(self) -> None:
        await asyncio.sleep(FIRST_DELAY)
        await asyncio.to_thread(legacy.migrate)
        while True:
            try:
                await self.cycle()
            except Exception as exc:
                log.warning("Ciclo della libreria musicale non riuscito: %s", exc)
            self.wake.clear()
            await self.idle()

    def view(self) -> dict:
        return {**state, "scan": dict(scanner.progress), "organizer": {k: v for k, v in organizer.progress.items()}}


library = LibraryService()
