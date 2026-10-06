import unittest
from unittest import mock

from features.home_assistant.commands import HomeCommands


class FakeHome(HomeCommands):
    def __init__(self):
        self.states = {"alarm_control_panel.casa": {"state": "armed_away"}, "lock.ingresso": {"state": "locked"},
                       "light.sala": {"state": "on"}}
        self.entities = {"lock.ingresso": {"name": "Porta d'ingresso"}, "light.sala": {"name": "Luce sala"}}
        self.stats = {"commands": 0, "avg_ms": 0}
        self.sent = []
        self.db = mock.Mock()
        self.db.run = lambda fn: None

    async def _call(self, msg, timeout):
        self.sent.append((msg["domain"], msg["service"], tuple(msg["target"]["entity_id"])))


class HomeTwinIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def run_plan(self, calls, mode="enforce"):
        home = FakeHome()
        from features.twin.model import HomeState
        state = HomeState(home.states, {"people": 1})
        with mock.patch("features.home_assistant.commands.DEMO", False), \
                mock.patch("features.twin.service.Twin.snapshot", return_value=state), \
                mock.patch("features.twin.service.Twin.mode", return_value=mode):
            return home, await home.execute({"calls": calls}, "test", "voce")

    async def test_conflicting_call_never_reaches_home_assistant(self):
        home, result = await self.run_plan([{"domain": "light", "service": "turn_off", "entity_ids": ["light.sala"], "data": {}},
                                            {"domain": "lock", "service": "unlock", "entity_ids": ["lock.ingresso"], "data": {}}])
        self.assertTrue(result["ok"])
        self.assertEqual(home.sent, [("light", "turn_off", ("light.sala",))])
        self.assertEqual(result["twin"]["dropped"], [{"service": "lock.unlock", "entity": "lock.ingresso"}])

    async def test_fully_blocked_plan_sends_nothing(self):
        home, result = await self.run_plan([{"domain": "lock", "service": "unlock", "entity_ids": ["lock.ingresso"], "data": {}}])
        self.assertFalse(result["ok"])
        self.assertEqual(home.sent, [])

    async def test_warn_mode_still_executes(self):
        home, result = await self.run_plan([{"domain": "lock", "service": "unlock", "entity_ids": ["lock.ingresso"], "data": {}}], mode="warn")
        self.assertEqual(home.sent, [("lock", "unlock", ("lock.ingresso",))])
        self.assertTrue(result["twin"]["blocked"])


if __name__ == "__main__":
    unittest.main()
