import asyncio
import logging
import random
import time

from config import env_get
from state import store

from features.desktop import briefing
from features.desktop.news import news

log = logging.getLogger("atena.secretary")

PREFIX = "briefing:"
REFRESH = 20
TTL = 90
AWAY_AFTER = 30
OWNER_CACHE = 60
ROTATE = 75
SLOTS = 4
MIN_ROTATING = 2
URGENT = 65
WEATHER_TTL = 15 * 60


def pick(cards: list[tuple[str, tuple]], shown_at: dict, slots: int = SLOTS) -> list[str]:
    must = [n for n, c in cards if c[2] >= URGENT]
    rest = sorted((n for n, c in cards if c[2] < URGENT), key=lambda n: (shown_at.get(n, 0.0), random.random()))
    return must + rest[:max(MIN_ROTATING, slots - len(must))]


class Secretary:
    def __init__(self) -> None:
        self.owner_slug = ""
        self.owner_at = 0.0
        self.active = False
        self.last_seen = 0.0
        self.refreshed = 0.0
        self.paused = False
        self.chosen: list[str] = []
        self.rotated = 0.0
        self.rotation = 0
        self.shown_at: dict[str, float] = {}
        self.weather: tuple[float, tuple | None] = (0.0, None)

    @staticmethod
    def enabled() -> bool:
        return env_get("ATENA_SECRETARY", "1") != "0"

    def owner(self) -> str:
        if time.time() - self.owner_at > OWNER_CACHE:
            from features.people.identity import owner
            profile = owner()
            self.owner_slug = profile["slug"] if profile else ""
            self.owner_at = time.time()
        return self.owner_slug

    def sighting(self) -> tuple[bool, bool]:
        slug = self.owner()
        mine = [p for p in (store.presence or {}).get("people", []) if p.get("known") and p.get("slug") == slug]
        return bool(mine), any(p.get("near") for p in mine)

    def clear(self, desk) -> None:
        keys = [k for k in desk.instances if k.startswith(PREFIX)]
        for k in keys:
            desk.instances.pop(k, None)
        if keys:
            desk.publish()

    async def cards(self) -> list[tuple[str, tuple]]:
        out = []
        for name, collect in briefing.COLLECTORS.items():
            try:
                card = collect()
            except Exception:
                log.exception("Widget del proprietario: sezione %s non disponibile", name)
                continue
            if card:
                out.append((name, card))
        card = briefing.headlines(await news.headlines(), self.rotation)
        if card:
            out.append(("news", card))
        card = await self.forecast()
        if card:
            out.append(("weather", card))
        return out

    async def forecast(self) -> tuple | None:
        if time.time() - self.weather[0] < WEATHER_TTL:
            return self.weather[1]
        card = None
        try:
            from features.chat.skills.weather import weather_skill
            _, ui = await weather_skill("")
            panel = next((p for p in ui.get("panels", []) if p.get("type") == "forecast"), None)
            card = ("weather", panel["data"], 40) if panel else None
        except Exception as exc:
            log.warning("Meteo per i widget del proprietario non disponibile: %s", exc)
        self.weather = (time.time(), card)
        return card

    async def show(self, desk) -> None:
        now = time.time()
        rotate = now - self.rotated >= ROTATE or not self.chosen
        if rotate:
            self.rotation += 1
        cards = await self.cards()
        if rotate:
            self.chosen, self.rotated = pick(cards, self.shown_at), now
            self.shown_at.update({n: now for n in self.chosen})
        else:
            self.chosen += [n for n, c in cards if c[2] >= URGENT and n not in self.chosen]
        keep = {PREFIX + n for n in self.chosen}
        for key in [k for k in desk.instances if k.startswith(PREFIX) and k not in keep]:
            desk.hide(key=key)
        for name, (wid, data, priority) in cards:
            if name in self.chosen:
                desk.show(wid, data, key=PREFIX + name, ttl=TTL, priority=priority)
        self.refreshed = now

    async def step(self, desk) -> None:
        if not self.enabled():
            if self.active:
                self.active = False
                self.clear(desk)
            return
        now = time.time()
        present, near = self.sighting()
        if present:
            self.last_seen = now
        if desk.in_request():
            if self.active:
                self.active, self.paused = False, True
                self.clear(desk)
            return
        if not self.active and (near or (present and self.paused)):
            self.paused = False
            self.active, self.chosen = True, []
            store.event("INFO", "Widget del proprietario aperti sul display", "desk")
            await self.show(desk)
            return
        if now - self.last_seen > AWAY_AFTER:
            self.paused = False
        if self.active and now - self.last_seen > AWAY_AFTER:
            self.active = False
            self.clear(desk)
            return
        if self.active and present and now - self.refreshed >= REFRESH:
            await self.show(desk)

    async def run(self) -> None:
        from features.desktop.desk import desk
        while True:
            try:
                await self.step(desk)
            except Exception:
                log.exception("Widget del proprietario sul display")
            await asyncio.sleep(1)


secretary = Secretary()
