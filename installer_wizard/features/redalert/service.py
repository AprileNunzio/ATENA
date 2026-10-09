import asyncio
import logging

from config import env_get
from state import store

from features.redalert import broadcast, lights

log = logging.getLogger("atena.redalert")

REPEAT_AFTER = 25


def enabled() -> bool:
    return env_get("ATENA_REDALERT", "1") != "0"


def _flag(key: str) -> bool:
    return env_get(key, "1") != "0"


def seconds() -> int:
    try:
        return max(10, min(600, int(env_get("ATENA_REDALERT_SECONDS", "60"))))
    except ValueError:
        return 60


class RedAlert:
    def __init__(self) -> None:
        self.stop_event = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.message = ""

    @property
    def active(self) -> bool:
        return self.task is not None and not self.task.done()

    def trigger(self, message: str, duration: int | None = None) -> bool:
        if not enabled():
            return False
        self.message = str(message or "Attenzione, allarme in casa.")[:400]
        if self.active:
            return True
        self.stop_event = asyncio.Event()
        self.task = asyncio.create_task(self._run(duration or seconds()))
        return True

    def stop(self) -> None:
        self.stop_event.set()

    async def _run(self, duration: int) -> None:
        saved = lights.snapshot() if _flag("ATENA_REDALERT_LIGHTS") else {}
        store.event("ERROR", f"Allarme rosso: {self.message}", "alarm")
        jobs = []
        if saved:
            jobs.append(self._lights(list(saved), duration))
        if _flag("ATENA_REDALERT_CAST"):
            jobs.append(self._voice(duration))
        try:
            await asyncio.gather(*jobs)
        finally:
            if saved:
                try:
                    await lights.restore(saved)
                except Exception as exc:
                    log.error("Luci non ripristinate dopo l'allarme: %s", exc)
                    store.event("WARN", f"Luci non ripristinate dopo l'allarme: {exc}", "alarm")
            store.event("INFO", "Allarme rosso terminato", "alarm")

    async def _lights(self, entities: list[str], duration: int) -> None:
        try:
            await lights.flash(entities, self.stop_event, duration)
        except Exception as exc:
            log.error("Luci rosse non attivate: %s", exc)
            store.event("WARN", f"Luci rosse non attivate: {exc}", "alarm")

    async def _voice(self, duration: int) -> None:
        loop = asyncio.get_running_loop()
        end = loop.time() + duration
        while not self.stop_event.is_set() and loop.time() < end:
            try:
                names = await broadcast.announce(self.message)
            except Exception as exc:
                log.error("Messaggio urgente non inviato ai Chromecast: %s", exc)
                store.event("WARN", f"Messaggio urgente non inviato ai Chromecast: {exc}", "alarm")
                return
            if not names:
                return
            store.event("INFO", f"Messaggio urgente su: {', '.join(names)}", "alarm")
            try:
                await asyncio.wait_for(self.stop_event.wait(), REPEAT_AFTER)
            except asyncio.TimeoutError:
                continue


redalert = RedAlert()
