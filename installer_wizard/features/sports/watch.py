import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from config import env_get
from state import store

from features.sports import commands, events, football, spotlight
from features.sports.catalog import LIVE, POST
from features.sports.fetch import SportsUnavailable
from features.sports.prefs import prefs

log = logging.getLogger("atena.sports")
TICK = 5.0
LIVE_EVERY, NEAR_EVERY, IDLE_EVERY = 20.0, 60.0, 600.0
PROXIMITY_TTL, PROXIMITY_COOLDOWN = 40.0, 1800.0
BUSY_PRIORITY = 60
WIDGET_PRIORITY = {"goal": 85, "red": 70, "kickoff": 75, "soon": 65, "final": 70}
WIDGET_TTL = {"goal": 120, "red": 60, "kickoff": 90, "soon": 900, "final": 600}


def enabled() -> bool:
    return env_get("ATENA_SPORTS", "1") != "0"


def match_widget(card: dict) -> tuple[str, dict]:
    if "match" in card:
        return "sport_match", {"kind": card["kind"], "match": card["match"], "team": card.get("team"), "last": card.get("last")}
    return "f1_race", card


class SportsWatcher:
    def __init__(self) -> None:
        self.snapshot: dict[str, dict] = {}
        self.announced: dict[str, float] = {}
        self.present: set[str] = set()
        self.recalled: dict[str, float] = {}
        self.next_refresh = 0.0
        self.last_error = ""

    @staticmethod
    def _desk():
        from features.desktop.desk import desk
        return desk

    def _fans(self, match: dict, followed: dict) -> list[str]:
        fans: list[str] = []
        for side in ("home", "away"):
            fans += (followed.get((match["league"], match[side]["id"])) or {}).get("fans", [])
        return list(dict.fromkeys(fans))

    def _wants(self, fans: list[str], alert: str) -> tuple[bool, bool]:
        profiles = [prefs.get(f) for f in fans]
        return any(p["alerts"].get(alert, True) for p in profiles), any(p["voice"] for p in profiles)

    def _someone_home(self) -> bool:
        presence = store.presence if isinstance(store.presence, dict) else {}
        return bool(presence.get("people")) or presence.get("status") != "ok"

    def _emit(self, event: dict, followed: dict) -> None:
        if event["key"] in self.announced:
            return
        self.announced[event["key"]] = time.time()
        alert = "kickoff" if event["kind"] in ("soon", "kickoff") else "results" if event["kind"] == "final" else "goals"
        show, voice = self._wants(self._fans(event["match"], followed), alert)
        if not show:
            return
        desk = self._desk()
        desk.show("sport_match", {"kind": event["kind"], "match": event["match"], "highlight": event["text"]},
                  key=f"sport:{event['match']['id']}", ttl=WIDGET_TTL[event["kind"]], priority=WIDGET_PRIORITY[event["kind"]])
        if voice and event["kind"] in ("goal", "final", "kickoff") and self._someone_home():
            desk.show("notice", {"icon": "⚽", "title": event["match"]["league_name"], "text": event["text"],
                                 "announce": True, "speak": event["text"]}, key=f"sport-voice:{event['key']}", ttl=15)

    async def refresh(self) -> float:
        followed = prefs.followed_teams()
        if not followed:
            self.snapshot = {}
            return IDLE_EVERY
        ids_by_league: dict[str, set[str]] = {}
        for league, tid in followed:
            ids_by_league.setdefault(league, set()).add(tid)
        today = datetime.now(timezone.utc).date()
        fresh: dict[str, dict] = {}
        for league, ids in ids_by_league.items():
            for day in (today - timedelta(days=1), today):
                try:
                    rows = await football.scoreboard(league, None if day == today else day)
                except SportsUnavailable as exc:
                    self.last_error = str(exc)
                    continue
                fresh.update({m["id"]: m for m in rows if events.involves(m, ids)})
        for event in events.diff(self.snapshot, fresh):
            self._emit(event, followed)
        for mid, m in fresh.items():
            if m["state"] == LIVE:
                self._desk().show("sport_match", {"kind": "live", "match": m}, key=f"sport:{mid}", ttl=90,
                                  priority=WIDGET_PRIORITY["kickoff"] - 15)
        self.snapshot = fresh
        cutoff = time.time() - 3 * 86400
        self.announced = {k: v for k, v in self.announced.items() if v > cutoff}
        if any(m["state"] == LIVE for m in fresh.values()):
            return LIVE_EVERY
        soon = [m for m in fresh.values() if m["state"] != POST]
        return NEAR_EVERY if soon else IDLE_EVERY

    def _busy(self) -> bool:
        return any(w.get("priority", 0) >= BUSY_PRIORITY and not str(w.get("key", "")).startswith("sport")
                   for w in self._desk().active())

    async def proximity(self) -> None:
        presence = store.presence if isinstance(store.presence, dict) else {}
        now_present = {p["slug"] for p in presence.get("people", []) if p.get("known") and p.get("slug")}
        arrived, self.present = now_present - self.present, now_present
        for slug in arrived:
            p = prefs.get(slug)
            if not p["proximity"] or time.time() - self.recalled.get(slug, 0) < PROXIMITY_COOLDOWN or self._busy():
                continue
            cards = [c for c in await spotlight.for_profile(p) if spotlight.worth_showing(c)]
            if not cards:
                continue
            self.recalled[slug] = time.time()
            wid, data = match_widget(cards[0])
            self._desk().show(wid, {**data, "for": slug}, key=f"sport-near:{slug}", ttl=PROXIMITY_TTL, priority=55)

    async def run(self) -> None:
        while True:
            if enabled():
                try:
                    if time.time() >= self.next_refresh:
                        self.next_refresh = time.time() + await self.refresh()
                        await commands.refresh_index()
                    await self.proximity()
                except SportsUnavailable as exc:
                    self.last_error = str(exc)
                    self.next_refresh = time.time() + NEAR_EVERY
            await asyncio.sleep(TICK)


watcher = SportsWatcher()
