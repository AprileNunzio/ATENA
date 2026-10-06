import unittest
from datetime import datetime, timedelta

from features.habits.foresight import Foresight, predict

DAY0 = datetime(2026, 9, 7)


def row(dt, entity, state, kind="action"):
    return (dt.timestamp(), entity, state, dt.weekday(), dt.hour * 60 + dt.minute, 1, 0, kind)


def evenings(days=10, arrivals=True):
    rows = []
    for d in range(days):
        day = DAY0 + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        home = day.replace(hour=18, minute=0) + timedelta(minutes=d % 5)
        if arrivals:
            rows.append(row(home, "presence", "arrived", "arrival"))
        rows.append(row(home + timedelta(seconds=50), "light.salotto", "on"))
        rows.append(row(home + timedelta(seconds=70), "media_player.spotify", "playing"))
        rows.append(row(home + timedelta(seconds=90), "lock.ingresso", "unlocked"))
        rows.append(row(day.replace(hour=7), "light.bagno", "on"))
    return rows


NAMES = {"light.salotto": "Luce salotto", "media_player.spotify": "Spotify", "light.bagno": "Luce bagno"}


class PredictTest(unittest.TestCase):
    def test_arrival_and_time_window_predictions(self):
        now = (DAY0 + timedelta(days=11)).replace(hour=18, minute=5).timestamp()
        found = {(e, s): reason for e, s, _, reason in predict(evenings(), now, arrival=True)}
        self.assertIn(("light.salotto", "on"), found)
        self.assertIn(("media_player.spotify", "playing"), found)
        self.assertNotIn(("light.bagno", "on"), found)

    def test_unlocking_is_never_prepared(self):
        now = (DAY0 + timedelta(days=11)).replace(hour=18, minute=5).timestamp()
        self.assertNotIn("lock.ingresso", [p[0] for p in predict(evenings(), now, arrival=True)])

    def test_sparse_history_predicts_nothing(self):
        now = (DAY0 + timedelta(days=2)).replace(hour=18, minute=5).timestamp()
        self.assertEqual(predict(evenings(days=2), now, arrival=True), [])


class ForesightTest(unittest.TestCase):
    def setUp(self):
        self.now = (DAY0 + timedelta(days=11)).replace(hour=18, minute=5).timestamp()
        self.clock = [self.now]
        self.foresight = Foresight(clock=lambda: self.clock[0])
        self.foresight.arm(evenings(), NAMES, arrival=True)

    def test_armed_plan_fires_on_matching_command(self):
        plan = self.foresight.match("Atena, accendi la luce del salotto")
        self.assertEqual(plan["calls"][0]["domain"], "light")
        self.assertEqual(plan["calls"][0]["service"], "turn_on")
        self.assertEqual(plan["entities"], ["light.salotto"])
        self.assertEqual(self.foresight.hits, 1)
        self.assertEqual(self.foresight.match("metti Spotify")["calls"][0]["service"], "media_play")

    def test_wrong_verb_or_entity_does_not_fire(self):
        self.assertIsNone(self.foresight.match("spegni la luce del salotto"))
        self.assertIsNone(self.foresight.match("accendi la luce della cucina"))
        self.assertIsNone(self.foresight.match("accendi"))

    def test_plans_expire(self):
        self.clock[0] += 3600
        self.assertIsNone(self.foresight.match("accendi la luce del salotto"))
        self.assertEqual(self.foresight.listing(), [])


if __name__ == "__main__":
    unittest.main()
