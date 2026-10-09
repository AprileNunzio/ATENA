from access import require_admin
from fastapi import APIRouter, Depends, HTTPException, Request
from state import store

from features.sports import football, spotlight
from features.sports.catalog import LEAGUES
from features.sports.fetch import SportsUnavailable
from features.sports.prefs import HOUSEHOLD, prefs
from features.sports.watch import match_widget, watcher

admin_routes = APIRouter()


def _people() -> list[dict]:
    from features.people import people
    rows = [{"slug": HOUSEHOLD, "name": "Tutta la casa", "role": "household"}]
    rows += [{"slug": p["slug"], "name": p.get("name") or p["slug"], "role": p.get("role", "")}
             for p in people.all_profiles(light=True)]
    return rows


def _known(slug: str) -> str:
    if slug not in {p["slug"] for p in _people()}:
        raise HTTPException(404, "Persona sconosciuta")
    return slug


@admin_routes.get("/api/sports")
async def sports_overview(_: str = Depends(require_admin)):
    people = _people()
    return {"leagues": [{"code": lg.code, "name": lg.name, "flag": lg.flag, "cup": lg.cup} for lg in LEAGUES],
            "people": people, "prefs": {p["slug"]: prefs.get(p["slug"]) for p in people},
            "live": list(watcher.snapshot.values()), "error": watcher.last_error}


@admin_routes.get("/api/sports/teams/{league}")
async def sports_teams(league: str, _: str = Depends(require_admin)):
    try:
        return {"teams": await football.teams(league)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except SportsUnavailable as exc:
        raise HTTPException(502, str(exc))


@admin_routes.put("/api/sports/prefs/{slug}")
async def sports_save(slug: str, request: Request, user: str = Depends(require_admin)):
    try:
        saved = prefs.put(_known(slug), await request.json())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    watcher.next_refresh = 0
    store.event("INFO", f"Preferenze sportive di {slug} aggiornate da {user}", "sports")
    return saved


@admin_routes.get("/api/sports/preview/{slug}")
async def sports_preview(slug: str, _: str = Depends(require_admin)):
    return {"cards": await spotlight.for_profile(prefs.get(_known(slug)))}


@admin_routes.post("/api/sports/show/{slug}")
async def sports_show(slug: str, _: str = Depends(require_admin)):
    cards = await spotlight.for_profile(prefs.get(_known(slug)))
    if not cards:
        raise HTTPException(404, "Niente da mostrare: aggiungi una squadra o la Formula 1")
    from features.desktop.desk import desk
    wid, data = match_widget(cards[0])
    desk.show(wid, data, key=f"sport-test:{slug}", ttl=60, priority=70)
    return {"ok": True, "widget": wid}
