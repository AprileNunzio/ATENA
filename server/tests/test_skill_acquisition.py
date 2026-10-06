import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

from server.features.sandbox.application.gateway import SandboxGateway
from server.features.sandbox.domain.strength import Strength
from server.features.skill_synthesis.application.acquisition import SkillAcquisition
from server.features.skill_synthesis.application.ports import SynthesisUnavailable
from server.features.skill_synthesis.application.runner import DynamicToolRunner
from server.features.skill_synthesis.application.synthesizer import SynthesisOutcome, ToolSynthesizer
from server.features.skill_synthesis.infrastructure.tool_store import JsonToolStore
from server.tests.test_skill_synthesis import Approval, RecordingPort, ScriptedCompletion, model_answer, report, tool

KEY = "a" * 64


class SignedStoreTest(unittest.TestCase):
    def test_signed_tools_round_trip(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonToolStore(root, lambda: KEY)
            store.save(tool())
            self.assertEqual(store.get("meteo_attuale").source, tool().source)
            self.assertEqual([t.name for t in store.all()], ["meteo_attuale"])
            self.assertEqual(os.stat(os.path.join(root, "meteo_attuale.json")).st_mode & 0o777, 0o600)

    def test_tampered_source_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonToolStore(root, lambda: KEY)
            store.save(tool())
            path = os.path.join(root, "meteo_attuale.json")
            data = json.loads(Path(path).read_text())
            data["source"] = data["source"] + "\nimport os; os.system('id')"
            Path(path).write_text(json.dumps(data))
            self.assertIsNone(store.get("meteo_attuale"))
            self.assertEqual(store.all(), [])

    def test_unsigned_or_foreign_key_files_are_refused(self):
        with tempfile.TemporaryDirectory() as root:
            JsonToolStore(root).save(tool())
            self.assertIsNone(JsonToolStore(root, lambda: KEY).get("meteo_attuale"))
            JsonToolStore(root, lambda: "b" * 64).save(tool())
            self.assertIsNone(JsonToolStore(root, lambda: KEY).get("meteo_attuale"))

    def test_file_renamed_to_shadow_another_tool_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonToolStore(root, lambda: KEY)
            store.save(tool())
            os.replace(os.path.join(root, "meteo_attuale.json"), os.path.join(root, "apri_porta.json"))
            self.assertIsNone(store.get("apri_porta"))
            self.assertEqual(store.all(), [])


class IsolationStrengthTest(unittest.IsolatedAsyncioTestCase):
    async def test_offline_tools_require_the_microvm(self):
        port = RecordingPort(report('{"summary": "ok"}', strength=3))
        runner = DynamicToolRunner(SandboxGateway(port), min_strength=Strength.MICROVM, egress_min_strength=Strength.USERSPACE_KERNEL)
        run = await runner.run(tool(egress_hosts=()), {})
        self.assertTrue(run.ok)
        self.assertEqual(port.specs[0].min_strength, Strength.MICROVM)

    async def test_networked_tools_require_their_own_floor(self):
        port = RecordingPort(report('{"summary": "ok"}', strength=2))
        runner = DynamicToolRunner(SandboxGateway(port), min_strength=Strength.MICROVM, egress_min_strength=Strength.USERSPACE_KERNEL)
        self.assertTrue((await runner.run(tool(), {})).ok)
        self.assertEqual(port.specs[0].min_strength, Strength.USERSPACE_KERNEL)

    async def test_weaker_backend_is_refused(self):
        port = RecordingPort(report('{"summary": "ok"}', strength=1))
        runner = DynamicToolRunner(SandboxGateway(port), min_strength=Strength.MICROVM)
        run = await runner.run(tool(egress_hosts=()), {})
        self.assertFalse(run.ok)
        self.assertIn("strength", run.error)


class FakeSynthesizer:
    def __init__(self, outcome=None, error=None, delay=0.0):
        self.outcome, self.error, self.delay, self.calls = outcome, error, delay, 0

    async def synthesize(self, goal, context=None):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.outcome


class AcquisitionTest(unittest.IsolatedAsyncioTestCase):
    async def test_end_to_end_tool_is_built_verified_stored_and_answers(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonToolStore(root, lambda: KEY)
            port = RecordingPort(report('{"summary": "Temperatura 21"}', strength=2))
            runner = DynamicToolRunner(SandboxGateway(port), min_strength=Strength.MICROVM, egress_min_strength=Strength.USERSPACE_KERNEL)
            synthesizer = ToolSynthesizer(ScriptedCompletion(model_answer()), runner, store, Approval(), clock=lambda: 5.0)
            outcome = await SkillAcquisition(synthesizer).acquire("che tempo fa a Milano")
            self.assertTrue(outcome.ok)
            self.assertEqual(outcome.speech, "Temperatura 21")
            self.assertEqual(outcome.tool_name, "meteo_attuale")
            self.assertIsNotNone(store.get("meteo_attuale"))

    async def test_concurrent_identical_goals_share_one_synthesis(self):
        fake = FakeSynthesizer(SynthesisOutcome(True, tool(), type("R", (), {"data": {"summary": "x"}})(), 1, "ok"), delay=0.05)
        acquisition = SkillAcquisition(fake)
        results = await asyncio.gather(*(acquisition.acquire("Prezzo  del bitcoin") for _ in range(3)),
                                       acquisition.acquire("prezzo del BITCOIN"))
        self.assertEqual(fake.calls, 1)
        self.assertTrue(all(r.ok for r in results))

    async def test_hourly_budget_stops_runaway_synthesis(self):
        now = [0.0]
        fake = FakeSynthesizer(SynthesisOutcome(False, None, None, 3, "no"))
        acquisition = SkillAcquisition(fake, per_hour=2, clock=lambda: now[0])
        for goal in ("a", "b"):
            await acquisition.acquire(goal)
        blocked = await acquisition.acquire("c")
        self.assertFalse(blocked.ok)
        self.assertIn("limite", blocked.message)
        self.assertEqual(fake.calls, 2)
        now[0] = 3601.0
        await acquisition.acquire("c")
        self.assertEqual(fake.calls, 3)

    async def test_failures_are_reported_not_raised(self):
        unavailable = await SkillAcquisition(FakeSynthesizer(error=SynthesisUnavailable("nessun modello"))).acquire("x")
        self.assertFalse(unavailable.ok)
        self.assertIn("nessun modello", unavailable.speech)
        self.assertFalse((await SkillAcquisition(FakeSynthesizer()).acquire("   ")).ok)


if __name__ == "__main__":
    unittest.main()
