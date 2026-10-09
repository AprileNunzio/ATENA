import asyncio
import logging

from config import env_get

from features.tv.m3u import PlaylistError
from features.tv.store import tv_store

log = logging.getLogger("atena.tv")
CHECK_EVERY = 1800.0


def refresh_hours() -> float:
    try:
        return max(1.0, min(168.0, float(env_get("ATENA_TV_REFRESH_H", "24"))))
    except ValueError:
        return 24.0


async def run() -> None:
    while True:
        await asyncio.sleep(CHECK_EVERY)
        for pid in tv_store.stale(refresh_hours() * 3600):
            try:
                await tv_store.refresh(pid)
            except PlaylistError as exc:
                log.info("Playlist TV %s non aggiornata: %s", pid, exc)
