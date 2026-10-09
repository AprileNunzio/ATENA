import asyncio
import logging

from state import store

from features.brain.journey import journeys
from features.flows.composition import studio

log = logging.getLogger("atena.flows")
CHECK_SECONDS = 30


def outcomes() -> list[tuple[float, str]]:
    return [(float(j.get("started") or 0), str(j.get("state") or "")) for j in journeys.snapshot()["journeys"]]


async def run() -> None:
    while True:
        await asyncio.sleep(CHECK_SECONDS)
        try:
            result = await studio.safeguard(outcomes())
        except ValueError as exc:
            log.warning("Controllo del flusso non riuscito: %s", exc)
            continue
        if result:
            store.event("WARN", f"Flusso riportato da solo alla versione precedente: {result['version']['note']}", "flows")
