import asyncio

from state import store as system_store

from features.places.locate import locator

FACE_EVERY = 2.0


def face_clues() -> int:
    presence = system_store.presence if isinstance(system_store.presence, dict) else {}
    noted = 0
    for p in presence.get("people", []):
        state = (p.get("liveness") or {}).get("state", "") if isinstance(p.get("liveness"), dict) else ""
        if p.get("known") and p.get("slug") and state != "spoof":
            locator.note(p["slug"], "face", "camera:main", float(p.get("confidence") or 0.5))
            noted += 1
    return noted


async def run() -> None:
    while True:
        face_clues()
        await asyncio.sleep(FACE_EVERY)
