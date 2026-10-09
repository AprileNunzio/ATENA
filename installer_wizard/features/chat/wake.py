import asyncio
import logging
import random
import time
from datetime import datetime, timedelta

import httpx
from state import store

from features.chat import context as request_context

from features.chat import speaker
from features.chat.wake_phrases import native, phrases
from features.google import timing

log = logging.getLogger("atena.assistant")
TRANSLATE_SECONDS = 4.0
_recent: list[str] = []


def _pick(options: tuple) -> str:
    fresh = [o for o in options if o not in _recent] or list(options)
    choice = random.choice(fresh)
    _recent.append(choice)
    del _recent[:-6]
    return choice


def _systems(words: dict) -> tuple[str, list[str]]:
    broken = [c.get("label", "") for c in (store.components or {}).values() if c.get("status") not in ("ok", None)]
    if not broken:
        return _pick(words["all_ok"]), []
    return words["watch"].format(names=", ".join(broken[:2])), broken


async def _next_event() -> dict | None:
    from features.google.gservices import google
    from features.people import identity
    profile = identity.current()
    session = google.for_profile(profile) if profile else None
    if not session or not session.ready("calendar"):
        return None
    now = datetime.now().astimezone()
    events = timing.upcoming(await session.events(now, now + timedelta(hours=12), 8), now)
    return events[0] if events else None


async def _weather() -> dict | None:
    from features.chat.skills.weather import weather_skill
    _, ui = await weather_skill("")
    panel = next((p for p in ui.get("panels", []) if p.get("type") == "forecast"), None)
    return (panel or {}).get("data", {}).get("current")


async def _safe(coro, timeout: float):
    try:
        return await asyncio.wait_for(coro, timeout)
    except (asyncio.TimeoutError, httpx.HTTPError, ValueError, KeyError, LookupError) as exc:
        log.debug("Informazione per il saluto non disponibile: %s", exc)
        return None


def wake_language() -> str:
    from features.locale import service
    from features.people import identity
    profile = identity.current()
    slug = str((profile or {}).get("slug") or "")
    device = request_context.device.get() or ""
    choice = service.chosen(slug, device)
    return choice.lang if choice else service.preferred(slug)


async def _translated(text: str, lang: str) -> str:
    from features.locale.pivot import pivot
    try:
        return await asyncio.wait_for(pivot.from_pivot(text, lang, force=True), TRANSLATE_SECONDS)
    except asyncio.TimeoutError:
        log.info("Traduzione del saluto troppo lenta: resta in italiano")
        return text


async def greeting(lang: str = "it") -> dict:
    words = phrases(lang)
    who = speaker.name() or words["who"]
    status, broken = _systems(words)
    event, weather = await asyncio.gather(_safe(_next_event(), 3.0), _safe(_weather(), 3.0))
    parts = [_pick(words["openers"]).format(who=who), status]
    hour = time.localtime().tm_hour
    if hour < 5 or hour >= 23:
        parts.append(_pick(words["late"]))
    items = []
    if event:
        minutes = timing.minutes_until(event["start"], datetime.now().astimezone())
        if minutes <= 90:
            parts.append(f"{timing.when(minutes).capitalize()} ha {event['title']}." if lang == "it"
                         else words["event"].format(time=event["start"].strftime("%H:%M"), title=event["title"]))
        items.append({"icon": "📅", "value": event["start"].strftime("%H:%M"), "label": event["title"][:24]})
    if weather:
        items.append({"icon": "🌡", "value": f"{weather.get('temp')}°", "label": str(weather.get("desc", ""))[:24]})
    items.append({"icon": "🛡" if not broken else "⚠️", "value": "OK" if not broken else str(len(broken)),
                  "label": words["systems"] if not broken else words["check"]})
    reply, ask = " ".join(parts), words["help"]
    if not native(lang):
        reply, ask = await asyncio.gather(_translated(reply, lang), _translated(ask, lang))
    return {"reply": reply, "lang": lang, "card": {"kind": "brief", "who": who, "items": items[:3], "text": ask}}
