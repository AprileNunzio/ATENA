import asyncio
from datetime import datetime, timedelta, timezone

from features.sports import football, formula1
from features.sports.catalog import BY_CODE, LIVE, POST, PRE
from features.sports.fetch import SportsUnavailable

RECENT = timedelta(hours=12)
TODAY = timedelta(hours=14)


def _age(m: dict, now: datetime) -> timedelta:
    try:
        return now - datetime.fromisoformat(m["start"].replace("Z", "+00:00"))
    except ValueError:
        return timedelta.max


async def team_card(team: dict, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    league, tid = team["league"], team["id"]
    try:
        today, fixtures, results = await asyncio.gather(
            football.scoreboard(league), football.team_fixtures(league, tid), football.team_results(league, tid))
    except SportsUnavailable:
        return None
    mine = [m for m in today if tid in (m["home"]["id"], m["away"]["id"])]
    live = next((m for m in mine if m["state"] == LIVE), None)
    if live:
        return {"rank": 0, "kind": "live", "match": live, "team": team}
    soon = next((m for m in football.upcoming(fixtures + mine) if -_age(m, now) <= TODAY), None)
    last = max((m for m in results + [m for m in mine if m["state"] == POST]), key=lambda m: m["start"], default=None)
    if soon:
        return {"rank": 1, "kind": "today", "match": soon, "team": team, "last": last}
    if last and _age(last, now) <= RECENT:
        return {"rank": 2, "kind": "result", "match": last, "team": team}
    nxt = next(iter(football.upcoming(fixtures)), None)
    if nxt:
        return {"rank": 3, "kind": "next", "match": nxt, "team": team, "last": last}
    return {"rank": 4, "kind": "result", "match": last, "team": team} if last else None


async def f1_card(now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    try:
        races, last = await asyncio.gather(formula1.schedule(), formula1.last_results())
    except SportsUnavailable:
        return None
    weekend = formula1.next_weekend(races, now)
    if weekend and weekend["live"]:
        return {"rank": 0, "mode": "live", "race": weekend, "session": weekend["live"]}
    if last and last.get("start") and now - datetime.fromisoformat(last["start"]) <= RECENT:
        return {"rank": 2, "mode": "results", "race": last, "results": last["results"][:10]}
    if weekend and weekend["next_session"]:
        start = datetime.fromisoformat(weekend["next_session"]["start"])
        rank = 1 if start - now <= TODAY else 3
        return {"rank": rank, "mode": "next", "race": weekend, "session": weekend["next_session"]}
    return None


async def standings_card(league: str, highlight: set[str] | None = None) -> dict:
    rows = await football.standings(league)
    return {"league": league, "league_name": BY_CODE[league].name, "rows": rows[:20], "highlight": sorted(highlight or [])}


async def f1_standings_card() -> dict:
    drivers, teams = await asyncio.gather(formula1.driver_standings(), formula1.constructor_standings())
    return {"rank": 5, "mode": "standings", "drivers": drivers[:10], "teams": teams[:10]}


async def for_profile(p: dict) -> list[dict]:
    cards = await asyncio.gather(*(team_card(t) for t in p["teams"]), f1_card() if p["f1"] else asyncio.sleep(0))
    out = [c for c in cards if isinstance(c, dict)]
    return sorted(out, key=lambda c: c["rank"])


def worth_showing(card: dict) -> bool:
    return card["rank"] <= 2


def state_of(card: dict) -> str:
    if "match" in card:
        return card["match"]["state"]
    return {"live": LIVE, "results": POST}.get(card.get("mode"), PRE)
