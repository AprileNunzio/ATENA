from datetime import datetime, timedelta, timezone

from features.sports.fetch import get_json

BASE = "https://api.jolpi.ca/ergast/f1/current"
SESSIONS = (("FirstPractice", "Prove libere 1"), ("SecondPractice", "Prove libere 2"), ("ThirdPractice", "Prove libere 3"),
            ("SprintQualifying", "Qualifiche sprint"), ("Sprint", "Sprint"), ("Qualifying", "Qualifiche"))
DURATION = {"Gara": timedelta(hours=2, minutes=15), "Sprint": timedelta(minutes=50), "Qualifiche": timedelta(hours=1, minutes=10),
            "Qualifiche sprint": timedelta(minutes=50)}
DEFAULT_DURATION = timedelta(hours=1)


def _when(block: dict) -> str:
    day, time = str(block.get("date") or ""), str(block.get("time") or "00:00:00Z")
    return f"{day}T{time.replace('Z', '')}+00:00" if day else ""


def _driver(d: dict) -> dict:
    return {"code": str(d.get("code") or d.get("familyName", "")[:3]).upper()[:3],
            "name": f"{d.get('givenName', '')} {d.get('familyName', '')}".strip()[:60]}


def parse_race(r: dict) -> dict:
    circuit = r.get("Circuit") or {}
    location = circuit.get("Location") or {}
    sessions = [{"name": label, "start": _when(r[key])} for key, label in SESSIONS if isinstance(r.get(key), dict)]
    sessions.append({"name": "Gara", "start": _when(r)})
    return {"round": int(r.get("round") or 0), "name": str(r.get("raceName") or "")[:60],
            "circuit": str(circuit.get("circuitName") or "")[:80],
            "place": ", ".join(x for x in (location.get("locality"), location.get("country")) if x)[:80],
            "start": _when(r), "sessions": sorted((s for s in sessions if s["start"]), key=lambda s: s["start"])}


def session_state(session: dict, now: datetime) -> str:
    start = datetime.fromisoformat(session["start"])
    end = start + DURATION.get(session["name"], DEFAULT_DURATION)
    return "pre" if now < start else "in" if now < end else "post"


async def schedule() -> list[dict]:
    data = await get_json(f"{BASE}.json", 21600)
    return [parse_race(r) for r in ((data.get("MRData") or {}).get("RaceTable") or {}).get("Races") or []]


def next_weekend(races: list[dict], now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    for race in races:
        if not race["sessions"]:
            continue
        last = race["sessions"][-1]
        if session_state(last, now) != "post":
            live = next((s for s in race["sessions"] if session_state(s, now) == "in"), None)
            upcoming = next((s for s in race["sessions"] if session_state(s, now) == "pre"), None)
            return {**race, "live": live, "next_session": upcoming}
    return None


async def last_results() -> dict | None:
    data = await get_json(f"{BASE}/last/results.json", 900)
    races = ((data.get("MRData") or {}).get("RaceTable") or {}).get("Races") or []
    if not races:
        return None
    race = races[0]
    rows = [{"pos": int(x.get("position") or 0), **_driver(x.get("Driver") or {}),
             "team": str((x.get("Constructor") or {}).get("name") or "")[:40],
             "time": str((x.get("Time") or {}).get("time") or x.get("status") or "")[:20],
             "points": float(x.get("points") or 0)} for x in race.get("Results") or []]
    return {**parse_race(race), "results": rows[:20]}


async def driver_standings() -> list[dict]:
    data = await get_json(f"{BASE}/driverStandings.json", 3600)
    lists = ((data.get("MRData") or {}).get("StandingsTable") or {}).get("StandingsLists") or [{}]
    return [{"pos": int(x.get("position") or 0), **_driver(x.get("Driver") or {}), "points": float(x.get("points") or 0),
             "wins": int(x.get("wins") or 0), "team": str(((x.get("Constructors") or [{}])[0]).get("name") or "")[:40]}
            for x in lists[0].get("DriverStandings") or []]


async def constructor_standings() -> list[dict]:
    data = await get_json(f"{BASE}/constructorStandings.json", 3600)
    lists = ((data.get("MRData") or {}).get("StandingsTable") or {}).get("StandingsLists") or [{}]
    return [{"pos": int(x.get("position") or 0), "team": str((x.get("Constructor") or {}).get("name") or "")[:40],
             "points": float(x.get("points") or 0), "wins": int(x.get("wins") or 0)}
            for x in lists[0].get("ConstructorStandings") or []]
