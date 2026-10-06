import unittest
from unittest import mock

from config import write_env
from features.desktop import desk as desk_module
from features.desktop import privacy as privacy_module
from state import store

OK = {"status": "ok", "people": [{"name": "Ann", "known": True}], "summary": ""}
EMPTY = {"status": "ok", "people": [], "summary": ""}


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class PrivacyTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        for target in (desk_module.time, privacy_module.time):
            patcher = mock.patch.object(target, "time", self.clock.time)
            patcher.start()
            self.addCleanup(patcher.stop)
        write_env({"ATENA_PRIVACY_AUTOCLOSE": "1", "ATENA_PRIVACY_AWAY_S": "10", "ATENA_PRIVACY_VOICE_S": "30"})
        self.addCleanup(lambda: write_env({"ATENA_PRIVACY_AUTOCLOSE": "1", "ATENA_PRIVACY_AWAY_S": "10", "ATENA_PRIVACY_VOICE_S": "30"}))
        privacy_module.privacy.gone_since = None
        self.addCleanup(lambda: setattr(store, "presence", {"status": "starting", "people": [], "summary": ""}))
        store.presence = OK
        self.desk = desk_module.Desk()
        self.desk.scan()

    def sweep(self, seconds: float = 0.0) -> bool:
        self.clock.advance(seconds)
        return self.desk.sweep_private()

    def test_personal_widgets_are_flagged_and_others_are_not(self):
        for wid in ("g_notify", "contact_card", "document_viewer", "route", "cam_stream", "reminder"):
            self.assertTrue(self.desk.widgets[wid]["personal"], wid)
        for wid in ("weather", "system_monitor", "music"):
            self.assertFalse(self.desk.widgets[wid]["personal"], wid)

    def test_personal_widgets_close_after_the_user_leaves_and_others_stay(self):
        self.desk.show("g_notify", {"x": 1})
        self.desk.show("weather", {"x": 1})
        self.assertFalse(self.sweep())
        store.presence = EMPTY
        self.assertFalse(self.sweep())
        self.assertFalse(self.sweep(9))
        self.assertTrue(self.sweep(2))
        ids = {i["id"] for i in self.desk.instances.values()}
        self.assertEqual(ids, {"weather"})
        self.assertTrue(store.privacy["away"])

    def test_returning_users_do_not_lose_new_widgets(self):
        store.presence = EMPTY
        self.sweep()
        self.sweep(11)
        store.presence = OK
        self.sweep()
        self.desk.show("g_notify", {"x": 1})
        self.assertFalse(self.sweep(5))
        self.assertIn("g_notify", {i["id"] for i in self.desk.instances.values()})

    def test_voice_opened_personal_widgets_close_after_thirty_seconds(self):
        self.desk.show("document_viewer", {"x": 1}, intent=True)
        self.desk.show("weather", {"x": 1}, intent=True)
        self.assertFalse(self.sweep(29))
        self.assertTrue(self.sweep(2))
        self.assertEqual({i["id"] for i in self.desk.instances.values()}, {"weather"})

    def test_reopening_by_voice_restarts_the_timer(self):
        self.desk.show("document_viewer", {"x": 1}, intent=True)
        self.sweep(25)
        self.desk.show("document_viewer", {"x": 2}, intent=True)
        self.assertFalse(self.sweep(10))
        self.assertTrue(self.sweep(25))

    def test_widgets_not_opened_by_voice_follow_only_the_presence_rule(self):
        self.desk.show("g_notify", {"x": 1})
        self.assertFalse(self.sweep(300))
        self.assertIn("g_notify", {i["id"] for i in self.desk.instances.values()})

    def test_bound_personal_widgets_are_not_reopened_while_away(self):
        self.desk.widgets["g_notify"]["bind"] = "mail_state"
        self.desk.sources["mail_state"] = lambda: {"unread": 3}
        self.desk._bindings()
        self.assertIn("bind:g_notify", self.desk.instances)
        store.presence = EMPTY
        self.sweep()
        self.sweep(11)
        self.desk._bindings()
        self.assertNotIn("bind:g_notify", self.desk.instances)
        store.presence = OK
        self.sweep()
        self.desk._bindings()
        self.assertIn("bind:g_notify", self.desk.instances)

    def test_no_camera_means_no_away_decision(self):
        store.presence = {"status": "error", "people": [], "summary": ""}
        self.desk.show("g_notify", {"x": 1})
        self.assertFalse(self.sweep(600))
        self.assertFalse(store.privacy["away"])

    def test_the_whole_thing_can_be_switched_off_and_tuned(self):
        write_env({"ATENA_PRIVACY_AUTOCLOSE": "0"})
        self.desk.show("document_viewer", {"x": 1}, intent=True)
        store.presence = EMPTY
        self.assertFalse(self.sweep(600))
        write_env({"ATENA_PRIVACY_AUTOCLOSE": "1", "ATENA_PRIVACY_VOICE_S": "0", "ATENA_PRIVACY_AWAY_S": "60"})
        store.presence = OK
        self.sweep()
        self.desk.show("document_viewer", {"x": 1}, intent=True)
        self.assertFalse(self.sweep(600))
        store.presence = EMPTY
        self.assertFalse(self.sweep())
        self.assertFalse(self.sweep(30))
        self.assertTrue(self.sweep(40))

    def test_state_snapshot_tells_the_display_the_policy(self):
        self.sweep()
        snap = store.snapshot()
        self.assertEqual(snap["privacy"], {"enabled": True, "away": False, "voice_s": 30})


if __name__ == "__main__":
    unittest.main()
