import json
import logging
import os
import time
from datetime import datetime, timedelta

import httpx

from config import STATE_DIR, env_get
from state import store

from features.google import timing
from features.maps import departure
from features.maps.travel_stats import TravelStats

log = logging.getLogger("atena.maps")
STATE_FILE = STATE_DIR / "maps_trips.json"
STATS_FILE = STATE_DIR / "maps_travel_stats.json"
GO_WINDOW = 6.0
UPDATE_SHIFT = 8.0
RECHECK = 300.0
FAR_RECHECK = 600.0


def number(key: str, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(env_get(key, str(default)))))
    except ValueError:
        return default


def enabled() -> bool:
    return env_get("ATENA_MAPS_TRIPS", "1") != "0"


class Trips:

    def __init__(self) -> None:
        self.state: dict[str, dict] = {}
        self.stats = TravelStats(STATS_FILE)
        try:
            self.state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log.warning("Stato dei viaggi non letto: %s", exc)

    def save(self) -> None:
        cutoff = time.time() - 86400
        self.state = {k: v for k, v in self.state.items() if float(v.get("start", 0)) > cutoff}
        try:
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state), encoding="utf-8")
            os.replace(tmp, STATE_FILE)
        except OSError as exc:
            log.warning("Stato dei viaggi non salvato: %s", exc)

    async def estimate(self, maps, origin: dict, dest: dict, mode: str, start: datetime, kind: str | None, now: datetime) -> dict:
        live = await maps.route(origin, dest, mode)
        buffer = departure.buffer_minutes(kind, env_get)
        minimum = number("ATENA_MAPS_MARGIN_MIN", 5.0, 0.0, 60.0)
        wise = env_get("ATENA_MAPS_WISE", "1") != "0"
        best, used = live, live
        first = departure.wise_margin(self.stats.samples(dest, start), live["minutes"], minimum, wise)
        guess = start - timedelta(minutes=live["minutes"] + buffer + first["margin"])
        if live["engine"] == "google" and mode in ("drive", "moto") and (guess - now).total_seconds() > 120:
            try:
                used = await maps.route(origin, dest, mode, depart_at=guess)
            except (httpx.HTTPError, ValueError, LookupError) as exc:
                log.info("Previsione del traffico per le %s non disponibile: %s", f"{guess:%H:%M}", exc)
        self.stats.record(dest, now, live["minutes"])
        margin = departure.wise_margin(self.stats.samples(dest, start), used["minutes"], minimum, wise)
        p = departure.plan(start, now, used["minutes"], buffer, margin["margin"])
        return {"route": best, "used": used, "buffer": buffer, "margin": margin, "plan": p, "live": live["engine"] == "google"}

    def announce(self, maps, e: dict, est: dict, origin: dict, dest: dict, kind: str | None, stage: str, now: datetime) -> None:
        from features.desktop.desk import desk
        used, p = est["used"], est["plan"]
        data = maps.card(origin, dest, used, arrive=e["start"].replace(tzinfo=None), title=e["title"])
        data["leave_by"] = p["leave"].strftime("%H:%M")
        data["speak"] = departure.speech(stage, e["title"], kind, e["start"], now, used["minutes"], used["delay_minutes"],
                                         est["live"], est["buffer"], est["margin"], p)
        data["announce"] = True
        data["advice"] = {"basis": est["margin"]["basis"], "samples": est["margin"]["samples"], "margin": est["margin"]["margin"]}
        desk.show("route", data, key=f"route:event:{e['id']}", ttl=max(600, (e["start"] - now).total_seconds() + 300))
        store.event("INFO", f"Viaggio «{e['title']}»: parti entro le {p['leave']:%H:%M} ({stage})", "maps")

    async def handle(self, maps, e: dict, now: datetime) -> None:
        key = f"event:{e['id']}"
        st = self.state.setdefault(key, {"stage": 0, "next": 0.0, "leave": 0.0, "start": e["start"].timestamp()})
        if time.time() < st["next"]:
            return
        kind = departure.classify(e["title"], e["where"])
        if not e["where"]:
            if kind and not st.get("missing"):
                st["missing"] = 1
                from features.desktop.desk import desk
                text = (f"Ha {departure.LABELS[kind]} alle {e['start']:%H:%M}, ma nell'evento non c'è il luogo di partenza: "
                        "aggiungilo e ti dirò quando uscire.")
                desk.show("notice", {"icon": "🧭", "title": e["title"], "text": text, "announce": True, "speak": text},
                          key=f"trip-missing:{e['id']}", ttl=900)
            return
        origin = await maps.home()
        dest = await maps.resolve(e["where"])
        est = await self.estimate(maps, origin, dest, maps.default_mode(), e["start"], kind, now)
        leave_ts = est["plan"]["leave"].timestamp()
        until = (est["plan"]["leave"] - now).total_seconds() / 60
        headsup = number("ATENA_MAPS_HEADSUP_MIN", 90.0, 10.0, 720.0)
        stage = st["stage"]
        if stage == 0:
            if until > headsup:
                st["next"] = time.time() + max(FAR_RECHECK, (until - headsup) * 30)
                return
            self.announce(maps, e, est, origin, dest, kind, "plan", now)
            st.update(stage=1, leave=leave_ts, next=time.time() + RECHECK)
        elif until > GO_WINDOW:
            shifted = abs(leave_ts - st["leave"]) / 60 >= UPDATE_SHIFT
            if shifted:
                self.announce(maps, e, est, origin, dest, kind, "update", now)
                st["leave"] = leave_ts
            st["next"] = time.time() + RECHECK
        elif stage == 1:
            self.announce(maps, e, est, origin, dest, kind, "go", now)
            st.update(stage=2, leave=leave_ts, next=time.time() + 3600)

    async def check(self, maps) -> None:
        if not enabled():
            return
        from features.google.gservices import google
        horizon = number("ATENA_MAPS_EVENT_HOURS", 4.0, 1.0, 48.0)
        now = datetime.now().astimezone()
        for _, session in google.present_sessions("calendar"):
            events = timing.upcoming(await session.events(now, now + timedelta(hours=horizon), 10), now)
            for e in events:
                try:
                    await self.handle(maps, e, now)
                except (LookupError, httpx.HTTPError, ValueError) as exc:
                    log.info("Consiglio di partenza per «%s» non calcolato: %s", e["title"], exc)
                    self.state.setdefault(f"event:{e['id']}", {"stage": 0, "leave": 0.0, "start": e["start"].timestamp()})["next"] = time.time() + 3600
        self.save()


trips = Trips()


async def check(maps) -> None:
    await trips.check(maps)
