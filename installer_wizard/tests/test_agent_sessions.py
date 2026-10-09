import asyncio
import time
import unittest
from unittest import mock

from features.agent.agent import PENDING_TTL, Agent
from features.chat import context


def _as(device: str, voice: str = "") -> None:
    context.device.set(device)
    context.voice.set(voice)


class AgentSessionTests(unittest.TestCase):

    def setUp(self):
        self.agent = Agent()
        _as("kiosk", "nunzio")
        self.agent.pending[context.session_key()] = {"request": "cancella", "steps": [], "tool": "delete",
                                                     "args": {"path": "x"}, "at": time.time()}

    def test_other_device_does_not_see_the_pending_confirmation(self):
        _as("remote", "nunzio")
        self.assertFalse(self.agent.has_pending())
        _as("kiosk", "nunzio")
        self.assertTrue(self.agent.has_pending())

    def test_other_speaker_on_same_device_cannot_confirm(self):
        _as("kiosk", "ospite-1")
        with mock.patch.object(self.agent, "_execute") as execute:
            reply = asyncio.run(self.agent.confirm(True))
        execute.assert_not_called()
        self.assertEqual(reply, "Non avevo nulla in sospeso.")
        _as("kiosk", "nunzio")
        self.assertTrue(self.agent.has_pending())

    def test_drop_only_removes_the_current_session(self):
        _as("admin")
        self.agent.pending[context.session_key()] = {"at": time.time()}
        self.agent.drop_pending()
        self.assertEqual(list(self.agent.pending), ["kiosk|nunzio"])

    def test_expired_confirmations_are_discarded(self):
        self.agent.pending["kiosk|nunzio"]["at"] = time.time() - PENDING_TTL - 1
        self.assertFalse(self.agent.has_pending())
        self.assertEqual(self.agent.pending, {})


if __name__ == "__main__":
    unittest.main()
