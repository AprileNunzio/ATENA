import asyncio
import logging
import time

log = logging.getLogger("atena.ducking")

TV_FRESH = 6 * 3600
TIMEOUT = 8


class Target:
    kind = ""

    def __init__(self, ident: str, name: str, original: float) -> None:
        self.ident, self.name, self.original, self.ducked = ident, name, original, original

    async def set(self, value: float) -> None:
        raise NotImplementedError

    async def current(self) -> float | None:
        return None


class MusicTarget(Target):
    kind = "music"

    async def set(self, value: float) -> None:
        from features.music.outputs import outputs
        session = outputs.sessions.get(self.ident)
        if session is not None:
            await outputs.apply(outputs.device(self.ident), session, "volume", value)

    async def current(self) -> float | None:
        from features.music.outputs import outputs
        session = outputs.sessions.get(self.ident)
        return session.volume if session is not None else None


class CastTarget(Target):
    kind = "cast"

    async def set(self, value: float) -> None:
        from features.music import cast_chrome, dlna
        from features.music.outputs import outputs
        device = outputs.device(self.ident)
        await (cast_chrome.control(device, "volume", value) if device["kind"] == "cast" else dlna.control(device, "volume", value))


class SpotifyTarget(Target):
    kind = "spotify"

    async def set(self, value: float) -> None:
        from features.spotify.spotify import spotify
        await spotify.set_volume(round(value * 100))

    async def current(self) -> float | None:
        from features.spotify.spotify import spotify
        pct = await spotify.playing_volume()
        return None if pct is None else pct / 100


class HomeTarget(Target):
    kind = "home"

    async def set(self, value: float) -> None:
        from features.home_assistant.home import brain
        await brain._call({"type": "call_service", "domain": "media_player", "service": "volume_set",
                           "service_data": {"volume_level": round(value, 2)}, "target": {"entity_id": [self.ident]}}, 10)

    async def current(self) -> float | None:
        from features.home_assistant.home import brain
        level = ((brain.states.get(self.ident) or {}).get("attrs") or {}).get("volume_level")
        return float(level) if isinstance(level, (int, float)) else None


async def probe(coro, label: str):
    try:
        return await asyncio.wait_for(coro, TIMEOUT)
    except Exception as exc:
        log.info("Volume: %s non disponibile (%s)", label, exc)
        return None


async def attempt(coro, label: str) -> bool:
    try:
        await asyncio.wait_for(coro, TIMEOUT)
        return True
    except Exception as exc:
        log.info("Volume: %s non regolabile (%s)", label, exc)
        return False


def music() -> list[Target]:
    from features.music.outputs import outputs
    out = []
    for device_id, session in outputs.sessions.items():
        device = outputs.devices.get(device_id) or {}
        if session.state == "playing" and device.get("kind") != "display":
            out.append(MusicTarget(device_id, device.get("name", device_id), session.volume))
    return out


async def tv(skip: set[str]) -> list[Target]:
    from features.music import cast_chrome, dlna
    from features.music.outputs import outputs
    from features.tv.targets import CASTING
    now, out = time.time(), []
    for target_id, at in list(CASTING.items()):
        if now - at > TV_FRESH:
            CASTING.pop(target_id, None)
            continue
        if target_id in skip or target_id not in outputs.devices:
            continue
        device = outputs.devices[target_id]
        info = await probe(cast_chrome.status(device) if device["kind"] == "cast" else dlna.status(device), device.get("name", target_id))
        if info and info.get("state") == "playing" and isinstance(info.get("volume"), (int, float)) and info["volume"] > 0:
            out.append(CastTarget(target_id, device.get("name", target_id), float(info["volume"])))
    return out


async def spotify_target() -> list[Target]:
    from features.spotify.spotify import spotify
    if not spotify.configured() or not spotify.current():
        return []
    pct = await probe(spotify.playing_volume(), "Spotify")
    return [SpotifyTarget("spotify", "Spotify", pct / 100)] if pct else []


def home() -> list[Target]:
    from features.home_assistant.home import brain
    if brain.status != "online":
        return []
    out = []
    for eid, st in brain.states.items():
        level = (st.get("attrs") or {}).get("volume_level")
        if eid.startswith("media_player.") and st.get("state") == "playing" and isinstance(level, (int, float)) and level > 0:
            out.append(HomeTarget(eid, (st.get("attrs") or {}).get("friendly_name") or eid, float(level)))
    return out
