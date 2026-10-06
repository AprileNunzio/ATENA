import asyncio
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from features.google import notify, timing
from features.maps import departure, trips
from features.maps.travel_stats import TravelStats


def now_at(h, m=0):
    return datetime.now().astimezone().replace(hour=h, minute=m, second=0, microsecond=0)


def event(eid, title, start, where="", all_day=False):
    return {"id": eid, "title": title, "where": where, "start": start, "all_day": all_day, "kind": "appointment"}


class TimingTest(unittest.TestCase):
    def test_a_trip_that_already_started_is_never_upcoming(self):
        now = now_at(11, 49)
        trip = event("t", "Viaggio", now_at(10, 5))
        later = event("l", "Dentista", now_at(14, 0))
        self.assertEqual(timing.upcoming([trip, later], now), [later])
        self.assertEqual(timing.ongoing([trip, later], now), [trip])

    def test_all_day_events_and_small_grace(self):
        now = now_at(10, 0)
        self.assertEqual(timing.upcoming([event("a", "Festa", now, all_day=True)], now), [])
        just_started = event("j", "Riunione", now - timedelta(seconds=10))
        self.assertEqual(timing.upcoming([just_started], now), [just_started])

    def test_when_never_says_one_minute_for_the_past(self):
        self.assertEqual(timing.when(-100), "adesso")
        self.assertEqual(timing.when(0.4), "adesso")
        self.assertEqual(timing.when(1), "tra 1 minuto")
        self.assertEqual(timing.when(12), "tra 12 minuti")
        self.assertEqual(timing.when(60), "tra 1 ora")
        self.assertEqual(timing.when(135), "tra 2 ore e 15 minuti")


class ReminderRegressionTest(unittest.TestCase):
    def setUp(self):
        self.file = Path(tempfile.mkdtemp()) / "reminded.json"
        patcher = mock.patch.object(notify, "REMINDED_FILE", self.file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.profile = {"slug": "nunzio", "first_name": "Nunzio"}
        self.shown = []

    def notifier(self):
        n = notify.Notifier()
        n._show = lambda profile, kind, data, key, ttl=0: self.shown.append(data)
        return n

    @staticmethod
    def session(events):
        class Fake:
            async def events(self, start, end, limit):
                return events
        return Fake()

    def test_ongoing_trip_is_not_announced_as_in_one_minute(self):
        trip = event("t", "Pullman per Roma", datetime.now().astimezone() - timedelta(hours=1, minutes=44))
        asyncio.run(self.notifier().soon(self.profile, self.session([trip]), 15))
        self.assertEqual(self.shown, [])

    def test_upcoming_event_is_announced_once_and_remembered_across_restarts(self):
        soon = event("s", "Dentista", datetime.now().astimezone() + timedelta(minutes=7, seconds=20))
        first = self.notifier()
        asyncio.run(first.soon(self.profile, self.session([soon]), 15))
        self.assertEqual(len(self.shown), 1)
        self.assertIn("tra 7 minuti ha Dentista", self.shown[0]["speak"])
        asyncio.run(self.notifier().soon(self.profile, self.session([soon]), 15))
        self.assertEqual(len(self.shown), 1)
        self.assertTrue(json.loads(self.file.read_text(encoding="utf-8")))

    def test_event_starting_right_now_says_adesso(self):
        now_event = event("n", "Riunione", datetime.now().astimezone() + timedelta(seconds=10))
        asyncio.run(self.notifier().soon(self.profile, self.session([now_event]), 15))
        self.assertIn("adesso ha Riunione", self.shown[0]["speak"])

    def test_corrupt_reminder_file_is_ignored(self):
        self.file.write_text("{rotto", encoding="utf-8")
        self.assertEqual(notify.Notifier().reminded, {})


class DepartureTest(unittest.TestCase):
    def test_trip_kinds_are_recognised_from_title_or_place(self):
        self.assertEqual(departure.classify("Pullman Napoli-Roma", ""), "bus")
        self.assertEqual(departure.classify("Viaggio", "Autostazione di Salerno"), "bus")
        self.assertEqual(departure.classify("Frecciarossa 9612", ""), "train")
        self.assertEqual(departure.classify("Volo FR123", "Aeroporto di Capodichino"), "flight")
        self.assertIsNone(departure.classify("Dentista", "Via Roma 1"))

    def test_buffers_are_configurable_and_bounded(self):
        env = {"ATENA_MAPS_BUFFER_BUS": "25"}.get
        self.assertEqual(departure.buffer_minutes("bus", lambda k, d: env(k, d)), 25.0)
        self.assertEqual(departure.buffer_minutes("flight", lambda k, d: d), 120.0)
        self.assertEqual(departure.buffer_minutes(None, lambda k, d: d), 5.0)
        self.assertEqual(departure.buffer_minutes("bus", lambda k, d: "9999"), 300.0)
        self.assertEqual(departure.buffer_minutes("bus", lambda k, d: "boh"), 15.0)

    def test_margin_is_cautious_without_history_and_data_driven_with_it(self):
        none = departure.wise_margin([], 30, 5)
        self.assertEqual((none["basis"], none["margin"]), ("prudenza", 6.0))
        calm = departure.wise_margin([30, 31, 30, 32, 30, 31], 30, 5)
        self.assertEqual(calm["basis"], "storico")
        self.assertEqual(calm["margin"], 5.0)
        jammed = departure.wise_margin([25, 28, 30, 45, 60, 26, 29, 50], 30, 5)
        self.assertGreater(jammed["margin"], calm["margin"] + 8)
        self.assertLessEqual(jammed["margin"], 30 * 0.6)
        self.assertEqual(jammed["typical"][0] <= jammed["typical"][1], True)
        fixed = departure.wise_margin([25, 60] * 5, 30, 7, wise=False)
        self.assertEqual((fixed["basis"], fixed["margin"]), ("fisso", 7))

    def test_plan_flags_a_trip_that_cannot_be_made(self):
        now, start = now_at(10, 0), now_at(10, 20)
        ok = departure.plan(start, now, 20, 5, 5)
        self.assertEqual(ok["leave"], now_at(9, 50))
        self.assertTrue(ok["late"])
        self.assertFalse(ok["will_miss"])
        gone = departure.plan(start, now, 30, 15, 5)
        self.assertTrue(gone["will_miss"])
        far = departure.plan(now_at(12, 0), now, 30, 15, 5)
        self.assertFalse(far["late"] or far["tight"])

    def test_speech_for_each_stage(self):
        now, start = now_at(8, 0), now_at(10, 5)
        margin = {"margin": 8.0, "typical": (22, 31), "samples": 9, "basis": "storico"}
        p = departure.plan(start, now, 25, 15, 8)
        plan = departure.speech("plan", "Pullman per Roma", "bus", start, now, 25, 6, True, 15, margin, p)
        for part in ("il pullman delle 10:05", "25 minuti", "6 per il traffico", "tra 22 e 31", "15 minuti prima", "parta entro le 09:17"):
            self.assertIn(part, plan)
        go = departure.speech("go", "Pullman per Roma", "bus", start, now, 27, 8, True, 15, margin, p)
        self.assertIn("È ora di uscire per il pullman", go)
        update = departure.speech("update", "Dentista", None, start, now, 25, None, False, 5, margin, p)
        self.assertTrue(update.startswith("Aggiornamento sul traffico."))
        self.assertIn("stima senza dati sul traffico", update)
        missed = departure.plan(start, now_at(10, 0), 30, 15, 8)
        text = departure.speech("plan", "Pullman", "bus", start, now_at(10, 0), 30, 0, True, 15, margin, missed)
        self.assertIn("è molto probabile che lo perda", text)
        late = departure.plan(start, now_at(9, 40), 25, 5, 5)
        self.assertIn("parta subito", departure.speech("plan", "Dentista", None, start, now_at(9, 40), 25, 0, True, 5, margin, late))


class TravelStatsTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "s.json"
        self.stats = TravelStats(self.path)
        self.dest = {"label": "Autostazione di Salerno"}
        self.monday = datetime(2026, 10, 5, 9, 15)

    def test_samples_are_grouped_by_destination_daytype_and_nearby_hours(self):
        self.stats.record(self.dest, self.monday, 28, now=1000)
        self.stats.record(self.dest, self.monday + timedelta(hours=1), 35, now=1000)
        self.stats.record(self.dest, self.monday + timedelta(hours=3), 90, now=1000)
        self.stats.record({"label": "Altro"}, self.monday, 5, now=1000)
        self.assertEqual(sorted(self.stats.samples(self.dest, self.monday)), [28.0, 35.0])
        self.assertEqual(self.stats.samples(self.dest, datetime(2026, 10, 10, 9, 15)), [])

    def test_close_samples_are_ignored_and_history_is_bounded_and_persistent(self):
        self.assertTrue(self.stats.record(self.dest, self.monday, 28, now=1000))
        self.assertFalse(self.stats.record(self.dest, self.monday, 29, now=1100))
        for i in range(80):
            self.stats.record(self.dest, self.monday, 30 + i, now=2000 + i * 700)
        self.assertEqual(len(self.stats.samples(self.dest, self.monday)), 60)
        self.assertEqual(len(TravelStats(self.path).samples(self.dest, self.monday)), 60)

    def test_corrupt_file_is_ignored(self):
        self.path.write_text("[[", encoding="utf-8")
        self.assertEqual(TravelStats(self.path).data, {})


class FakeMaps:
    def __init__(self, minutes=25, delay=6, engine="google"):
        self.minutes, self.delay, self.engine = minutes, delay, engine
        self.calls = []

    @staticmethod
    def default_mode():
        return "drive"

    async def home(self):
        return {"name": "casa", "label": "casa", "lat": 40.0, "lon": 14.0}

    async def resolve(self, where):
        return {"name": where, "label": where, "lat": 40.1, "lon": 14.1}

    async def route(self, origin, dest, mode="drive", arrive_by=None, depart_at=None):
        self.calls.append(depart_at)
        return {"engine": self.engine, "mode": mode, "minutes": self.minutes, "base_minutes": self.minutes - self.delay,
                "delay_minutes": self.delay, "meters": 15000, "via": "A3", "tolls": False, "steps": [], "path": []}

    @staticmethod
    def card(origin, dest, r, arrive=None, title=""):
        return {"title": title, "leave_by": "", "minutes": round(r["minutes"])}


class TripsFlowTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        for name, value in (("STATE_FILE", self.dir / "t.json"),):
            patcher = mock.patch.object(trips, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.trips = trips.Trips()
        self.trips.stats = TravelStats(self.dir / "s.json")
        self.desk = mock.Mock()
        patcher = mock.patch("features.desktop.desk.desk", self.desk)
        patcher.start()
        self.addCleanup(patcher.stop)

    def spoken(self):
        return [c.args[1].get("speak") for c in self.desk.show.call_args_list]

    def run_handle(self, maps, ev, now):
        asyncio.run(self.trips.handle(maps, ev, now))

    def test_far_trip_is_not_announced_and_not_recomputed_every_minute(self):
        now = datetime.now().astimezone()
        ev = event("far", "Pullman per Roma", now + timedelta(hours=6), "Autostazione")
        maps = FakeMaps()
        self.run_handle(maps, ev, now)
        self.assertEqual(self.desk.show.call_count, 0)
        calls = len(maps.calls)
        self.run_handle(maps, ev, now)
        self.assertEqual(len(maps.calls), calls)
        self.assertGreater(self.trips.state["event:far"]["next"], time.time() + 500)

    def test_plan_then_go_stages_are_announced_once_each(self):
        now = datetime.now().astimezone()
        ev = event("bus", "Pullman per Roma", now + timedelta(minutes=70), "Autostazione di Salerno")
        maps = FakeMaps(minutes=25)
        self.run_handle(maps, ev, now)
        self.assertEqual(self.desk.show.call_count, 1)
        text = self.spoken()[0]
        self.assertIn("il pullman", text)
        self.assertIn("parta entro le", text)
        self.assertEqual(self.trips.state["event:bus"]["stage"], 1)
        self.run_handle(maps, ev, now)
        self.assertEqual(self.desk.show.call_count, 1)
        self.trips.state["event:bus"]["next"] = 0
        close = now + timedelta(minutes=10)
        self.run_handle(maps, ev, close)
        self.assertEqual(self.desk.show.call_count, 1)
        self.trips.state["event:bus"]["next"] = 0
        near = ev["start"] - timedelta(minutes=48)
        self.run_handle(maps, ev, near)
        self.assertEqual(self.desk.show.call_count, 2)
        self.assertIn("È ora di uscire", self.spoken()[1])
        self.assertEqual(self.trips.state["event:bus"]["stage"], 2)
        self.trips.state["event:bus"]["next"] = 0
        self.run_handle(maps, ev, near)
        self.assertEqual(self.desk.show.call_count, 2)

    def test_traffic_getting_worse_triggers_an_update_not_a_repeat(self):
        now = datetime.now().astimezone()
        ev = event("u", "Pullman", now + timedelta(minutes=120), "Autostazione")
        maps = FakeMaps(minutes=25)
        self.run_handle(maps, ev, now)
        self.assertEqual(self.desk.show.call_count, 1)
        self.trips.state["event:u"]["next"] = 0
        maps.minutes = 50
        self.run_handle(maps, ev, now + timedelta(minutes=10))
        self.assertEqual(self.desk.show.call_count, 2)
        self.assertTrue(self.spoken()[1].startswith("Aggiornamento sul traffico."))

    def test_predictive_traffic_is_requested_for_the_planned_departure(self):
        now = datetime.now().astimezone()
        ev = event("p", "Pullman", now + timedelta(minutes=80), "Autostazione")
        maps = FakeMaps(minutes=25)
        self.run_handle(maps, ev, now)
        self.assertIsNone(maps.calls[0])
        self.assertIsNotNone(maps.calls[1])

    def test_without_traffic_data_the_advice_says_so(self):
        now = datetime.now().astimezone()
        ev = event("o", "Pullman", now + timedelta(minutes=80), "Autostazione")
        self.run_handle(FakeMaps(engine="osm", delay=0), ev, now)
        self.assertIn("stima senza dati sul traffico", self.spoken()[0])

    def test_trip_without_a_place_asks_for_it_only_once(self):
        now = datetime.now().astimezone()
        ev = event("m", "Pullman per Roma", now + timedelta(hours=2), "")
        self.run_handle(FakeMaps(), ev, now)
        self.run_handle(FakeMaps(), ev, now)
        self.assertEqual(self.desk.show.call_count, 1)
        self.assertIn("luogo di partenza", self.desk.show.call_args.args[1]["text"])

    def test_plain_event_without_a_place_is_ignored(self):
        now = datetime.now().astimezone()
        self.run_handle(FakeMaps(), event("d", "Dentista", now + timedelta(hours=2), ""), now)
        self.assertEqual(self.desk.show.call_count, 0)

    def test_state_is_saved_and_old_entries_are_dropped(self):
        now = datetime.now().astimezone()
        self.run_handle(FakeMaps(), event("k", "Pullman", now + timedelta(minutes=70), "Autostazione"), now)
        self.trips.state["event:old"] = {"stage": 2, "start": time.time() - 3 * 86400}
        self.trips.save()
        saved = json.loads(trips.STATE_FILE.read_text(encoding="utf-8"))
        self.assertIn("event:k", saved)
        self.assertNotIn("event:old", saved)

    def test_check_skips_events_already_started_and_survives_failures(self):
        now = datetime.now().astimezone()
        started = event("s", "Pullman", now - timedelta(minutes=104), "Autostazione")
        coming = event("c", "Pullman 2", now + timedelta(minutes=70), "Autostazione")

        class Session:
            async def events(self, a, b, c):
                return [started, coming]

        class Google:
            @staticmethod
            def present_sessions(name):
                return [("x", Session())]

        class Broken(FakeMaps):
            async def resolve(self, where):
                raise LookupError(where)

        with mock.patch("features.google.gservices.google", Google()):
            asyncio.run(self.trips.check(FakeMaps()))
            self.assertEqual(self.desk.show.call_count, 1)
            self.assertNotIn("event:s", self.trips.state)
            self.trips.state.clear()
            asyncio.run(self.trips.check(Broken()))
            self.assertEqual(self.desk.show.call_count, 1)
            self.assertGreater(self.trips.state["event:c"]["next"], time.time() + 3000)


class GreetingRegressionTest(unittest.TestCase):
    def next_event(self, events):
        from features.chat import wake

        class Session:
            @staticmethod
            def ready(name):
                return True

            async def events(self, start, end, limit):
                return events

        google = mock.Mock()
        google.for_profile.return_value = Session()
        with mock.patch("features.people.identity.current", return_value={"slug": "n"}),                 mock.patch("features.google.gservices.google", google):
            return asyncio.run(wake._next_event())

    def test_trip_in_progress_is_not_the_next_event(self):
        trip = event("t", "Viaggio", datetime.now().astimezone() - timedelta(hours=1, minutes=44))
        self.assertIsNone(self.next_event([trip]))

    def test_the_first_future_event_is_chosen_over_one_in_progress(self):
        now = datetime.now().astimezone()
        trip = event("t", "Viaggio", now - timedelta(hours=1))
        later = event("l", "Cena", now + timedelta(hours=3))
        self.assertEqual(self.next_event([trip, later])["id"], "l")


if __name__ == "__main__":
    unittest.main()
