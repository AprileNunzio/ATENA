import asyncio
import unittest
from unittest import mock

from features.agent import registry
from features.team import runner
from features.team.board import board


class VerificationTest(unittest.TestCase):
    def setUp(self):
        board.messages.clear()
        patcher = mock.patch.object(runner, "SETTLE", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def register(self, verdicts: list):
        calls = []

        async def fn() -> str:
            calls.append(1)
            return "fatto"
        registry.TOOLS["zz_checked"] = {"name": "zz_checked", "description": "", "args": {}, "fn": fn, "confirm": False, "full_only": False,
                                        "agent": "music", "verify": lambda a, r: verdicts.pop(0)}
        self.addCleanup(registry.TOOLS.pop, "zz_checked")
        return calls

    def test_an_unconfirmed_result_is_retried_once_and_then_succeeds(self):
        calls = self.register(["non parte", None])
        self.assertEqual(asyncio.run(runner.run_as("zz_checked", {})), "fatto")
        self.assertEqual(len(calls), 2)
        self.assertEqual(board.messages[0]["kind"], "verifica")

    def test_a_result_that_is_never_confirmed_is_reported_as_failure(self):
        calls = self.register(["non parte", "ancora no"])
        with self.assertRaises(runner.NotVerified):
            asyncio.run(runner.run_as("zz_checked", {}))
        self.assertEqual(len(calls), 2)
        self.assertEqual(board.messages[-1]["kind"], "errore")

    def test_a_broken_check_does_not_hide_the_result(self):
        calls = self.register([])
        with self.assertRaises(runner.NotVerified):
            asyncio.run(runner.run_as("zz_checked", {}))
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
