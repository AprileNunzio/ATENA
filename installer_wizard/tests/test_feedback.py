import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from features.habits import feedback as feedback_module
from features.habits.feedback import WINDOW, Feedback, context
from features.habits.foresight import Foresight

T0 = datetime(2026, 9, 7, 18, 0).timestamp()


def ev(eid, to):
    return {"name": "state_changed", "data": {"entity_id": eid, "to": to}}


def plan(kind="automation", origin="a1", entity="cover.sala", service="close_cover"):
    domain = entity.split(".")[0]
    return {"calls": [{"domain": domain, "service": service, "entity_ids": [entity], "data": {}}], "origin": {"kind": kind, "id": origin}}


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(feedback_module, "FILE", Path(self.tmp.name) / "f.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = [T0]
        self.fb = Feedback(clock=lambda: self.now[0], environment=lambda: (1, False))
        self.ctx = context(T0, 1, False)

    def undo_once(self):
        self.fb.observe(plan(), "", "automazione", {"cover.sala": "open"})
        self.fb.on_event(ev("cover.sala", "closed"))
        self.now[0] += 60
        self.fb.on_event(ev("cover.sala", "open"))

    def test_user_reversal_is_a_penalty_and_silence_a_reward(self):
        self.undo_once()
        key = self.fb.key("automation", "a1", "cover.sala", "closed", self.ctx)
        self.assertEqual(self.fb.data["stats"][key]["undo"], 1)
        self.fb.observe(plan(), "", "automazione", {"cover.sala": "open"})
        self.now[0] += WINDOW + 1
        self.fb.sweep()
        self.assertEqual(self.fb.data["stats"][key]["ok"], 1)

    def test_repeated_reversals_suppress_only_that_context(self):
        for _ in range(3):
            self.undo_once()
        self.assertTrue(self.fb.suppressed("automation", "a1", "cover.sala", "closed", self.ctx))
        self.assertFalse(self.fb.suppressed("automation", "a1", "cover.sala", "closed", context(T0, 0, True)))
        self.assertFalse(self.fb.suppressed("voice", "a1", "cover.sala", "closed", self.ctx))

    def test_atena_echo_and_superseded_actions_are_not_reversals(self):
        self.fb.observe(plan(), "", "automazione", {"cover.sala": "open"})
        self.fb.on_event(ev("cover.sala", "open"))
        self.assertEqual(self.fb.data["stats"], {})
        self.fb.superseded(["cover.sala"])
        self.now[0] += 60
        self.fb.on_event(ev("cover.sala", "open"))
        self.assertEqual(self.fb.data["stats"], {})

    def test_learned_plans_are_forgotten_after_two_reversals(self):
        forgotten = []
        self.fb._forget_learned = forgotten.append
        for _ in range(2):
            self.fb.observe(plan(kind="learned", origin=""), "abbassa la tapparella", "memoria", {"cover.sala": "open"})
            self.now[0] += 10
            self.fb.on_event(ev("cover.sala", "open"))
        self.assertEqual(forgotten, ["abbassa la tapparella"])

    def test_state_is_persisted_privately_and_resettable(self):
        self.undo_once()
        self.fb.save()
        path = Path(self.tmp.name) / "f.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(Feedback().data["stats"]), 1)
        self.assertEqual(self.fb.reset(), 1)
        self.assertEqual(self.fb.listing(), [])


class ForesightRecalibrationTest(unittest.TestCase):
    def test_suppressed_predictions_are_not_armed(self):
        class Judge:
            def suppressed(self, kind, origin, entity, state):
                return entity == "light.salotto"

            def acceptance(self, kind, origin, entity, state):
                return 0.5

        from tests.test_foresight import NAMES, evenings
        now = datetime(2026, 9, 18, 18, 5).timestamp()
        armed = Foresight(clock=lambda: now, judge=Judge()).arm(evenings(), NAMES, arrival=True)
        entities = {a["entity"]: a["confidence"] for a in armed}
        self.assertNotIn("light.salotto", entities)
        self.assertLessEqual(entities["media_player.spotify"], 0.5)


if __name__ == "__main__":
    unittest.main()
