import asyncio
import logging
import secrets
import time

log = logging.getLogger("atena.redalert")

AUDIO_TTL = 600
VOLUME = 0.85
MAX_CLIPS = 8


class Clips:
    def __init__(self) -> None:
        self.items: dict[str, tuple[bytes, float]] = {}

    def add(self, wav: bytes) -> str:
        now = time.time()
        self.items = {k: v for k, v in self.items.items() if v[1] > now}
        while len(self.items) >= MAX_CLIPS:
            self.items.pop(min(self.items, key=lambda k: self.items[k][1]))
        token = secrets.token_urlsafe(24)
        self.items[token] = (wav, now + AUDIO_TTL)
        return token

    def get(self, token: str) -> bytes | None:
        hit = self.items.get(str(token or ""))
        return hit[0] if hit and hit[1] > time.time() else None


clips = Clips()


async def casts() -> list[dict]:
    from features.music.outputs import outputs
    await outputs.refresh()
    return [d for d in outputs.devices.values() if d.get("kind") == "cast"]


async def _one(device: dict, url: str) -> str | None:
    from features.music import cast_chrome
    try:
        await cast_chrome.control(device, "volume", VOLUME)
        await cast_chrome.load(device, url, {"title": "Allarme", "artist": "Atena", "album": "", "art": "", "mime": "audio/wav"})
        return device.get("name", "Chromecast")
    except RuntimeError as exc:
        log.warning("Messaggio urgente non riprodotto su %s: %s", device.get("name"), exc)
        return None


async def announce(text: str) -> list[str]:
    from features.tv.targets import base_url
    from features.voices import synthesis
    devices = await casts()
    if not devices:
        return []
    wav = await synthesis.synthesize(str(text)[:400])
    url = f"{base_url()}/api/redalert/audio/{clips.add(wav)}.wav"
    done = await asyncio.gather(*(_one(d, url) for d in devices))
    return [name for name in done if name]
