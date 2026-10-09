import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.agent import agent as agent_module
from features.agent import registry
from features.agent.agent import Agent
from features.autonomy import approvals, trust
from features.autonomy.trust import TrustBook

RPA_LS = {"node": "localhost", "steps": [{"do": "ls", "target": "/sys/class/sound-virtual/pcm0"}]}
MAIL = {"to": "a@b.c", "subject": "x", "body": "y"}


class Harness:
    def __init__(self, moves: list[dict]) -> None:
        self.root = tempfile.TemporaryDirectory()
        base = Path(self.root.name)
        self.book = TrustBook(base / "trust.json")
        self.patches = [
            mock.patch.object(trust, "book", self.book),
            mock.patch.object(approvals, "FILE", base / "approvals.json"),
            mock.patch.object(agent_module.Agent, "_decide", mock.AsyncMock(side_effect=moves)),
            mock.patch.object(agent_module.gate, "within_role", return_value=True),
            mock.patch.object(agent_module.gate, "tool", return_value=mock.Mock(allowed=True)),
            mock.patch.object(agent_module, "level", return_value="completo"),
        ]

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()
        self.root.cleanup()


def answer(text="fatto"):
    return {"answer": text}


class AutonomyApprovalTest(unittest.IsolatedAsyncioTestCase):
    async def test_reported_case_invalid_rpa_step_never_reaches_approval(self):
        with Harness([{"tool": "rpa_run", "args": RPA_LS}, answer("controllato")]):
            agent = Agent()
            agent.on_approval = mock.AsyncMock()
            steps: list = []
            result = await agent.run("diagnosi", steps, auto="Diagnosi: Ascolto vocale")
            agent.on_approval.assert_not_awaited()
            self.assertEqual(approvals.pending(), [])
            self.assertTrue(steps[0]["result"].startswith("ERRORE"))
            self.assertEqual(result, "controllato")

    async def test_diagnosis_is_read_only_and_never_asks(self):
        with Harness([{"tool": "send_email", "args": MAIL}, answer()]):
            agent = Agent()
            agent.on_approval = mock.AsyncMock()
            steps: list = []
            with mock.patch.object(registry, "needs_confirm", return_value=True), \
                    mock.patch.object(registry, "precheck", return_value=""):
                await agent.run("diagnosi", steps, auto="Diagnosi: Rete", readonly=True)
            agent.on_approval.assert_not_awaited()
            self.assertTrue(steps[0]["result"].startswith("NEGATO"))

    async def test_duplicates_rejections_and_always_approve(self):
        move = {"tool": "send_email", "args": MAIL}
        with Harness([move, move, move, answer(), move, answer()]) as h:
            agent = Agent()
            agent.on_approval = mock.AsyncMock()
            with mock.patch.object(registry, "needs_confirm", return_value=True), \
                    mock.patch.object(registry, "precheck", return_value=""), \
                    mock.patch.object(Agent, "_execute", mock.AsyncMock()) as execute:
                await agent.run("manda", [], auto="Compito")
                await agent.run("manda", [], auto="Compito")
                self.assertEqual(agent.on_approval.await_count, 1)
                self.assertEqual(len(approvals.pending()), 1)
                h.book.reject("send_email", MAIL)
                approvals.take(approvals.pending()[0]["id"])
                steps: list = []
                await agent.run("manda", steps, auto="Compito")
                self.assertTrue(steps[0]["result"].startswith("NEGATO"))
                h.book.trust("send_email", MAIL, "Compito", "invio")
                await agent.run("manda", [], auto="Compito")
                execute.assert_awaited()
            self.assertEqual(len(h.book.rules()), 1)
            self.assertTrue(h.book.revoke(h.book.rules()[0]["id"]))


if __name__ == "__main__":
    unittest.main()
