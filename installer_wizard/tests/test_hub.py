import unittest

from features.hub import model


class HubModelTest(unittest.TestCase):
    def test_every_journey_kind_has_a_station_and_answer_is_last(self):
        self.assertEqual(model.station("input"), 0)
        self.assertEqual(model.station("answer"), len(model.STATIONS) - 1)
        self.assertEqual(model.station("something-new"), model.station("router"))

    def test_journey_view_reports_progress_and_failure(self):
        j = {"id": "a", "query": "q" * 300, "state": "done", "nodes": [{"k": "input", "s": "ok"}, {"k": "agent", "s": "ok"},
                                                                     {"k": "error", "s": "fail"}]}
        view = model.journey_view(j)
        self.assertEqual(view["reached"], len(model.STATIONS) - 1)
        self.assertTrue(view["failed"])
        self.assertEqual(len(view["query"]), 140)

    def test_desk_shows_active_call(self):
        active = [{"component": "research", "model": {"model": "qwen"}, "steps": [{"text": "cerco fonti"}]}]
        desk = model.desk_view("research", active, {})
        self.assertEqual((desk["busy"], desk["model"], desk["doing"]), (True, "qwen", "cerco fonti"))
        self.assertFalse(model.desk_view("conversation", active, {})["busy"])


if __name__ == "__main__":
    unittest.main()
