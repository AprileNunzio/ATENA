import re
from datetime import date, datetime, timedelta, timezone

from features.sports.catalog import BY_CODE, LIVE, POST, PRE
from features.sports.fetch import get_json

SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
CORE = "https://site.api.espn.com/apis/v2/sports/soccer"
_CODE = re.compile(r"^[a-z]{3,4}(\.[a-z0-9_]{1,16}){1,2}$")
_ID = re.compile(r"^\d{1,8}$")
_COLOR = re.compile(r"^[0-9a-fA-F]{6}$")


def check_league(code: str) -> str:
    if code not in BY_CODE or not _CODE.match(code):
        raise ValueError("Campionato sconosciuto")
    return code


def check_team(team_id: str) -> str:
    if not _ID.match(str(team_id or "")):
        raise ValueError("Squadra non valida")
    return str(team_id)


def _score(raw) -> int | None:
    if isinstance(raw, dict):
        raw = raw.get("displayValue", raw.get("value"))
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _team(t: dict) -> dict:
    color = str(t.get("color") or "")
    return {"id": str(t.get("id", "")), "name": str(t.get("displayName") or t.get("name") or "")[:60],
            "short": str(t.get("shortDisplayName") or t.get("displayName") or "")[:30],
            "abbr": str(t.get("abbreviation") or "")[:5], "color": color if _COLOR.match(color) else ""}


def _detail(d: dict, sides: dict) -> dict | None:
    kind = "goal" if d.get("scoringPlay") else "red" if d.get("redCard") else None
    if not kind:
        return None
    who = [str(a.get("displayName", ""))[:40] for a in d.get("athletesInvolved") or []]
    return {"kind": kind, "minute": str((d.get("clock") or {}).get("displayValue") or "")[:8],
            "side": sides.get(str((d.get("team") or {}).get("id", "")), ""), "player": who[0] if who else "",
            "own_goal": bool(d.get("ownGoal")), "penalty": bool(d.get("penaltyKick"))}


def parse_event(e: dict, league: str) -> dict | None:
    comp = (e.get("competitions") or [{}])[0]
    teams = {c.get("homeAway"): c for c in comp.get("competitors") or []}
    if "home" not in teams or "away" not in teams:
        return None
    status = comp.get("status") or e.get("status") or {}
    state = (status.get("type") or {}).get("state", PRE)
    sides = {str(teams[s]["team"].get("id", "")): s for s in ("home", "away")}
    events = [x for x in (_detail(d, sides) for d in comp.get("details") or []) if x]
    out = {"id": str(e.get("id", "")), "league": league, "league_name": BY_CODE[league].name if league in BY_CODE else league,
           "start": str(e.get("date", "")), "state": state if state in (LIVE, PRE, POST) else PRE,
           "clock": str(status.get("displayClock") or "")[:10],
           "detail": str((status.get("type") or {}).get("shortDetail") or "")[:40],
           "venue": str((comp.get("venue") or {}).get("fullName") or "")[:80], "events": events[:20]}
    for side in ("home", "away"):
        out[side] = {**_team(teams[side].get("team") or {}), "score": _score(teams[side].get("score"))}
    return out


async def scoreboard(league: str, day: date | None = None) -> list[dict]:
    check_league(league)
    stamp = (day or datetime.now(timezone.utc).date()).strftime("%Y%m%d")
    today = day is None or day == datetime.now(timezone.utc).date()
    data = await get_json(f"{SITE}/{league}/scoreboard?dates={stamp}", 30 if today else 900)
    return [m for m in (parse_event(e, league) for e in data.get("events") or []) if m]


async def team_fixtures(league: str, team_id: str) -> list[dict]:
    data = await get_json(f"{SITE}/{check_league(league)}/teams/{check_team(team_id)}/schedule?fixture=true", 1800)
    return [m for m in (parse_event(e, league) for e in data.get("events") or []) if m]


async def team_results(league: str, team_id: str) -> list[dict]:
    data = await get_json(f"{SITE}/{check_league(league)}/teams/{check_team(team_id)}/schedule", 600)
    rows = [m for m in (parse_event(e, league) for e in data.get("events") or []) if m]
    return [m for m in rows if m["state"] == POST]


async def teams(league: str) -> list[dict]:
    data = await get_json(f"{SITE}/{check_league(league)}/teams", 86400)
    raw = ((data.get("sports") or [{}])[0].get("leagues") or [{}])[0].get("teams") or []
    return sorted((_team(t.get("team") or {}) for t in raw), key=lambda t: t["name"])


def parse_standings(data: dict) -> list[dict]:
    rows = []
    for child in data.get("children") or [{"standings": data.get("standings") or {}}]:
        for entry in (child.get("standings") or {}).get("entries") or []:
            stats = {s.get("name"): s.get("value") for s in entry.get("stats") or []}
            rows.append({**_team(entry.get("team") or {}), "rank": int(stats.get("rank") or 0),
                         "played": int(stats.get("gamesPlayed") or 0), "points": int(stats.get("points") or 0),
                         "won": int(stats.get("wins") or 0), "drawn": int(stats.get("ties") or 0),
                         "lost": int(stats.get("losses") or 0), "diff": int(stats.get("pointDifferential") or 0)})
    rows.sort(key=lambda r: (r["rank"] or 999, -r["points"]))
    return rows


async def standings(league: str) -> list[dict]:
    return parse_standings(await get_json(f"{CORE}/{check_league(league)}/standings", 900))


def upcoming(matches: list[dict], horizon_days: int = 21) -> list[dict]:
    now = datetime.now(timezone.utc)
    limit = now + timedelta(days=horizon_days)
    keep = []
    for m in matches:
        try:
            start = datetime.fromisoformat(m["start"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if m["state"] != POST and start <= limit:
            keep.append(m)
    return sorted(keep, key=lambda m: m["start"])
