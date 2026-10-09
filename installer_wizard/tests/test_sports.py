import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from features.sports import commands, events, football, formula1, speech
from features.sports.prefs import SportsPrefs, clean

NOW = datetime(2026, 10, 11, 15, 30, tzinfo=timezone.utc)


def espn_event(state="in", home=0, away=0, details=None, start="2026-10-11T16:00Z"):
    return {"id": "401", "date": start, "competitions": [{
        "status": {"displayClock": "34'", "type": {"state": state, "shortDetail": "34'"}},
        "venue": {"fullName": "Maradona"}, "details": details or [],
        "competitors": [
            {"homeAway": "home", "score": str(home), "team": {"id": "114", "displayName": "Napoli", "shortDisplayName": "Napoli", "abbreviation": "NAP", "color": "12a0d7"}},
            {"homeAway": "away", "score": {"value": float(away), "displayValue": str(away)}, "team": {"id": "110", "displayName": "Internazionale", "shortDisplayName": "Inter", "abbreviation": "INT", "color": "zz"}}]}]}


GOAL = {"scoringPlay": True, "clock": {"displayValue": "34'"}, "team": {"id": "114"}, "athletesInvolved": [{"displayName": "Lukaku"}]}


class ParseTest(unittest.TestCase):
    def test_event_both_score_shapes_and_sanitised_color(self):
        m = football.parse_event(espn_event(home=2, away=1, details=[GOAL]), "ita.1")
        self.assertEqual((m["home"]["score"], m["away"]["score"]), (2, 1))
        self.assertEqual(m["away"]["color"], "")
        self.assertEqual(m["events"][0], {"kind": "goal", "minute": "34'", "side": "home", "player": "Lukaku", "own_goal": False, "penalty": False})

    def test_incomplete_event_is_skipped(self):
        self.assertIsNone(football.parse_event({"competitions": [{"competitors": []}]}, "ita.1"))

    def test_standings(self):
        data = {"children": [{"standings": {"entries": [
            {"team": {"id": "2", "displayName": "B"}, "stats": [{"name": "rank", "value": 2}, {"name": "points", "value": 10}]},
            {"team": {"id": "1", "displayName": "A"}, "stats": [{"name": "rank", "value": 1}, {"name": "points", "value": 13}]}]}}]}
        self.assertEqual([r["id"] for r in football.parse_standings(data)], ["1", "2"])

    def test_league_and_team_validation(self):
        for code in ("ita.1", "uefa.europa.conf", "ita.coppa_italia"):
            self.assertEqual(football.check_league(code), code)
        with self.assertRaises(ValueError):
            football.check_league("../../etc")
        with self.assertRaises(ValueError):
            football.check_team("12a")


class DiffTest(unittest.TestCase):
    def snap(self, **kw):
        m = football.parse_event(espn_event(**kw), "ita.1")
        return {m["id"]: m}

    def test_goal_kickoff_final(self):
        pre, live0 = self.snap(state="pre"), self.snap(state="in")
        self.assertEqual([e["kind"] for e in events.diff(pre, live0, NOW)], ["kickoff"])
        goal = events.diff(live0, self.snap(state="in", home=1, details=[GOAL]), NOW)
        self.assertEqual(goal[0]["kind"], "goal")
        self.assertIn("Lukaku", goal[0]["text"])
        final = events.diff(self.snap(state="in", home=1), self.snap(state="post", home=1), NOW)
        self.assertEqual([e["kind"] for e in final], ["final"])

    def test_kickoff_soon_only_inside_window(self):
        soon = events.diff({}, self.snap(state="pre", start="2026-10-11T15:40Z"), NOW)
        self.assertEqual([e["kind"] for e in soon], ["soon"])
        self.assertEqual(events.diff({}, self.snap(state="pre", start="2026-10-11T18:00Z"), NOW), [])

    def test_first_snapshot_announces_nothing_live(self):
        self.assertEqual(events.diff({}, self.snap(state="in", home=3), NOW), [])


class FormulaOneTest(unittest.TestCase):
    RACE = {"round": "18", "raceName": "Italian GP", "date": "2026-10-11", "time": "13:00:00Z",
            "Circuit": {"circuitName": "Monza", "Location": {"locality": "Monza", "country": "Italy"}},
            "Qualifying": {"date": "2026-10-10", "time": "14:00:00Z"}}

    def test_parse_and_live_session(self):
        race = formula1.parse_race(self.RACE)
        self.assertEqual([s["name"] for s in race["sessions"]], ["Qualifiche", "Gara"])
        live = formula1.next_weekend([race], datetime(2026, 10, 11, 13, 30, tzinfo=timezone.utc))
        self.assertEqual(live["live"]["name"], "Gara")
        before = formula1.next_weekend([race], datetime(2026, 10, 9, tzinfo=timezone.utc))
        self.assertEqual(before["next_session"]["name"], "Qualifiche")
        self.assertIsNone(formula1.next_weekend([race], datetime(2026, 10, 12, tzinfo=timezone.utc)))


class PrefsTest(unittest.TestCase):
    def test_clean_rejects_bad_teams_and_filters_codes(self):
        with self.assertRaises(ValueError):
            clean({"teams": [{"league": "x", "id": "1"}]})
        out = clean({"teams": [{"league": "ita.1", "id": "114", "name": "<b>Napoli</b>", "color": "nope"}] * 2,
                     "f1_drivers": ["lec", "toolong", "HAM"]})
        self.assertEqual(len(out["teams"]), 1)
        self.assertEqual(out["teams"][0]["name"], "bNapoli/b")
        self.assertEqual(out["f1_drivers"], ["LEC", "HAM"])

    def test_store_followed_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "sports.json"
            store = SportsPrefs(path)
            store.put("mario", {"teams": [{"league": "ita.1", "id": "114", "name": "Napoli"}], "f1": True})
            self.assertEqual(SportsPrefs(path).followed_teams()[("ita.1", "114")]["fans"], ["mario"])
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(SportsPrefs(path).everyone(), {})


class VoiceTest(unittest.TestCase):
    TEAMS = [{"league": "ita.1", "id": "110", "name": "Internazionale", "short": "Inter"},
             {"league": "ita.1", "id": "104", "name": "AS Roma", "short": "Roma"},
             {"league": "ita.1", "id": "103", "name": "AC Milan", "short": "Milan"}]

    def test_team_aliases(self):
        self.assertEqual(commands.find_team("com è finita l'inter?", self.TEAMS)["id"], "110")
        self.assertEqual(commands.find_team("risultato della roma", self.TEAMS)["id"], "104")
        self.assertIsNone(commands.find_team("che tempo fa domani", self.TEAMS))

    def test_league_words_need_whole_words(self):
        self.assertEqual(commands.find_league("classifica della serie a"), "ita.1")
        self.assertIsNone(commands.find_league("è obbligatorio"))

    def test_f1_trigger(self):
        self.assertTrue(commands.F1.search(commands.norm("Quando corre la Formula 1?")))
        self.assertFalse(commands.F1.search(commands.norm("accendi la luce")))


class SpeechTest(unittest.TestCase):
    def test_result_sentence(self):
        m = football.parse_event(espn_event(state="post", home=2, away=1, details=[GOAL], start="2026-10-10T18:45Z"), "ita.1")
        team = {"id": "114", "short": "Napoli", "name": "Napoli"}
        text = speech.match_speech({"kind": "result", "match": m}, team, NOW + timedelta(hours=1))
        self.assertTrue(text.startswith("Napoli ha vinto 2 a 1 contro Inter"))
        self.assertIn("Lukaku", text)


if __name__ == "__main__":
    unittest.main()
