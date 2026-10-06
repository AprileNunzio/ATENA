import json
import os
import tempfile
import unittest
from pathlib import Path

from server.core.kernel.consensus.ballot import Ballot
from server.core.kernel.consensus.critical import CriticalAction, IntentConsistencyVoter, is_critical
from server.core.kernel.consensus.jury import CriticalActionJury
from server.core.kernel.consensus.laws_book import FOUNDATION, LawsBook
from server.core.kernel.consensus.ledger import VerdictLedger
from server.core.kernel.consensus.panel import ConsensusPanel, byzantine_bounds
from server.core.kernel.domain.outcome import ConsensusVerdict
from server.tests.test_kernel_swarm import FixedVoter, destructive_dag

KEY = "c" * 64


class ModelVoter:
    def __init__(self, name, approve, model, can_veto=True):
        self.name, self.can_veto, self._approve, self._model = name, can_veto, approve, model

    async def vote(self, dag):
        return Ballot(self.name, self._approve, "ok" if self._approve else "no", self._model)


class ByzantineQuorumTest(unittest.IsolatedAsyncioTestCase):
    def test_bounds(self):
        self.assertEqual([byzantine_bounds(n) for n in (1, 2, 3, 4, 5, 7, 10)],
                         [(0, 1), (0, 2), (0, 2), (1, 3), (1, 4), (2, 5), (3, 7)])

    async def test_simple_majority_is_not_enough_once_a_traitor_is_possible(self):
        voters = [FixedVoter(n, n in "abc") for n in "abcde"]
        self.assertFalse((await ConsensusPanel(voters).vote(destructive_dag("x"))).approved)
        voters = [FixedVoter(n, n in "abcd") for n in "abcde"]
        self.assertTrue((await ConsensusPanel(voters).vote(destructive_dag("x"))).approved)

    async def test_one_model_impersonating_several_jurors_is_not_diversity(self):
        same = [FixedVoter("policy", True, can_veto=True), ModelVoter("critic", True, "ollama/m1"), ModelVoter("laws", True, "ollama/m1")]
        verdict = await ConsensusPanel(same, min_distinct_models=2).vote(destructive_dag("x"))
        self.assertFalse(verdict.approved)
        self.assertTrue(any(o.startswith("diversity") for o in verdict.objections))
        mixed = [FixedVoter("policy", True, can_veto=True), ModelVoter("critic", True, "ollama/m1"), ModelVoter("laws", True, "ollama/m2")]
        self.assertTrue((await ConsensusPanel(mixed, min_distinct_models=2).vote(destructive_dag("x"))).approved)


class ClassificationTest(unittest.TestCase):
    def test_critical_services(self):
        for args in (("lock", "unlock", "lock.ingresso"), ("alarm_control_panel", "alarm_disarm", "alarm_control_panel.casa"),
                     ("cover", "open_cover", "cover.garage"), ("valve", "open_valve", "valve.acqua"),
                     ("siren", "turn_off", "siren.esterna"), ("switch", "turn_off", "switch.allarme_perimetrale"),
                     ("homeassistant", "toggle", "lock.ingresso"), ("homeassistant", "turn_off", "light.x,alarm_control_panel.casa")):
            with self.subTest(args=args):
                self.assertTrue(is_critical(*args))

    def test_everyday_services_are_not_critical(self):
        for args in (("lock", "lock", "lock.ingresso"), ("light", "turn_on", "light.salotto"), ("cover", "open_cover", "cover.tapparella_sala"),
                     ("alarm_control_panel", "alarm_arm_away", "alarm_control_panel.casa"), ("homeassistant", "turn_off", "light.salotto")):
            with self.subTest(args=args):
                self.assertFalse(is_critical(*args))


class IntentConsistencyTest(unittest.IsolatedAsyncioTestCase):
    async def ballot(self, utterance, domain="lock", service="unlock", entity="lock.front_door"):
        return await IntentConsistencyVoter(CriticalAction(domain, service, entity, utterance)).vote(None)

    async def test_grounded_requests_pass(self):
        self.assertTrue((await self.ballot("Atena, apri la porta d'ingresso")).approve)
        self.assertTrue((await self.ballot("disattiva l'allarme", "alarm_control_panel", "alarm_disarm", "alarm_control_panel.casa")).approve)
        self.assertTrue((await self.ballot("apri il garage", "cover", "open_cover", "cover.garage")).approve)

    async def test_hallucinated_inverted_negated_or_retargeted_actions_are_vetoed(self):
        self.assertFalse((await self.ballot("chiudi la porta")).approve)
        self.assertFalse((await self.ballot("non aprire la porta")).approve)
        self.assertFalse((await self.ballot("leggimi le email di oggi")).approve)
        self.assertFalse((await self.ballot("apri il cancello")).approve)


class LedgerTest(unittest.TestCase):
    def test_chain_verifies_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "sub", "ledger.jsonl")
            ledger = VerdictLedger(path, lambda: KEY, clock=lambda: 1.0)
            ledger.append({"approved": False})
            ledger.append({"approved": False})
            self.assertTrue(VerdictLedger(path, lambda: KEY).verify())
            lines = Path(path).read_text().splitlines()
            entry = json.loads(lines[0])
            entry["event"]["approved"] = True
            lines[0] = json.dumps(entry)
            Path(path).write_text("\n".join(lines) + "\n")
            self.assertFalse(VerdictLedger(path, lambda: KEY).verify())

    def test_deleted_entries_break_the_chain(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "ledger.jsonl")
            ledger = VerdictLedger(path, lambda: KEY)
            for i in range(3):
                ledger.append({"i": i})
            lines = Path(path).read_text().splitlines()
            Path(path).write_text("\n".join(lines[1:]) + "\n")
            self.assertFalse(ledger.verify())


class JuryTest(unittest.IsolatedAsyncioTestCase):
    def jury(self, root, *llm, min_models=2):
        ledger = VerdictLedger(os.path.join(root, "ledger.jsonl"), lambda: KEY)
        return CriticalActionJury(lambda: list(llm), ledger, min_distinct_models=min_models), ledger

    async def test_unanimous_diverse_jury_approves_and_records(self):
        with tempfile.TemporaryDirectory() as root:
            jury, ledger = self.jury(root, ModelVoter("critic", True, "m1"), ModelVoter("laws", True, "m2"))
            verdict = await jury.judge(CriticalAction("lock", "unlock", "lock.ingresso", "apri la porta di ingresso"))
            self.assertTrue(verdict.approved)
            self.assertTrue(ledger.verify())
            self.assertIn("lock.unlock", Path(os.path.join(root, "ledger.jsonl")).read_text())

    async def test_any_single_objection_denies(self):
        with tempfile.TemporaryDirectory() as root:
            jury, _ = self.jury(root, ModelVoter("critic", False, "m1"), ModelVoter("laws", True, "m2"))
            self.assertFalse((await jury.judge(CriticalAction("lock", "unlock", "lock.ingresso", "apri la porta"))).approved)
            jury, _ = self.jury(root, ModelVoter("critic", True, "m1"), ModelVoter("laws", True, "m2"))
            self.assertFalse((await jury.judge(CriticalAction("lock", "unlock", "lock.ingresso", "chiudi la porta"))).approved)

    async def test_unwritable_audit_denies(self):
        with tempfile.TemporaryDirectory() as root:
            blocker = os.path.join(root, "file")
            Path(blocker).touch()
            ledger = VerdictLedger(os.path.join(blocker, "ledger.jsonl"), lambda: KEY)
            jury = CriticalActionJury(lambda: [ModelVoter("critic", True, "m1"), ModelVoter("laws", True, "m2")], ledger)
            verdict = await jury.judge(CriticalAction("lock", "unlock", "lock.ingresso", "apri la porta"))
            self.assertFalse(verdict.approved)
            self.assertTrue(any(o.startswith("ledger") for o in verdict.objections))


class LawsBookTest(unittest.TestCase):
    def test_foundation_is_always_present(self):
        book = LawsBook()
        self.assertEqual(book.text(), FOUNDATION)
        book.update("- non aprire mai la porta di notte")
        self.assertTrue(book.text().startswith(FOUNDATION))
        self.assertIn("di notte", book.text())
        book.update("")
        self.assertIn("di notte", book.text())


class HomeAgentGateTest(unittest.IsolatedAsyncioTestCase):
    async def test_critical_calls_go_to_the_jury_with_the_user_utterance(self):
        from server.features.home_assistant_bridge.ha_agent import HomeAssistantAgent, current_utterance

        class Jury:
            def __init__(self, approved):
                self.approved, self.seen = approved, []

            async def judge(self, action):
                self.seen.append(action)
                return ConsensusVerdict(self.approved, ("critic: no",))

        denying = Jury(False)
        agent = HomeAssistantAgent(token="", jury=denying)
        self.assertEqual(await agent.authorize("light", "turn_on", "light.salotto"), "")
        self.assertEqual(denying.seen, [])
        marker = current_utterance.set("apri la porta")
        try:
            self.assertTrue((await agent.authorize("lock", "unlock", "lock.ingresso")).startswith("DENIED"))
            self.assertEqual(await HomeAssistantAgent(token="", jury=Jury(True)).authorize("lock", "unlock", "lock.ingresso"), "")
        finally:
            current_utterance.reset(marker)
        self.assertEqual(denying.seen[0].utterance, "apri la porta")


if __name__ == "__main__":
    unittest.main()
