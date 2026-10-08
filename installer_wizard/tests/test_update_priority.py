import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import updater
from orchestrator import orch
from state import store
from steps import STEPS


class BootPriorityTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for s in STEPS:
            store.steps.pop(s.id, None)

    async def boot(self, newer: set, pipeline: bool = True, pending=None, failed_step: str = ""):
        reasons = []

        async def priority(reason):
            reasons.append(reason)
            return any(word in reason for word in newer)

        async def run_pipeline():
            if failed_step:
                store.steps[failed_step] = {"status": "failed"}
            return pipeline

        with ExitStack() as stack:
            patch = lambda *a, **k: stack.enter_context(mock.patch(*a, **k))
            patch("orchestrator.updater.priority_update", side_effect=priority)
            pipeline_mock = patch("orchestrator.run_pipeline", side_effect=run_pipeline)
            patch("orchestrator.updater.pending", return_value=pending)
            patch("orchestrator.DEMO", False)
            finish = patch("orchestrator.updater.finish_pending", new_callable=mock.AsyncMock, return_value=True)
            patch("orchestrator.updater.mark_good", new_callable=mock.AsyncMock)
            patch("orchestrator.health.probe_all", new_callable=mock.AsyncMock, return_value={})
            patch("orchestrator.health.publish")
            patch("orchestrator.packages.migrate")
            patch("setup_api.apply_answers_file", new_callable=mock.AsyncMock, return_value=False)
            patch("setup_api.done", return_value=True)
            patch("orchestrator.asyncio.sleep", new_callable=mock.AsyncMock)
            stack.enter_context(mock.patch.object(orch, "install_background", new_callable=mock.AsyncMock))
            await orch.boot()
        return reasons, pipeline_mock, finish

    async def test_a_fixed_version_online_wins_before_the_old_pipeline_runs(self):
        reasons, pipeline, _ = await self.boot(newer={"avvio"})
        self.assertEqual(reasons, ["prioritario all'avvio"])
        pipeline.assert_not_called()

    async def test_after_a_failure_a_newer_fix_is_preferred_to_rollback(self):
        reasons, _, finish = await self.boot(newer={"errore"}, pipeline=False, pending={"from": "a", "to": "b"})
        self.assertEqual(reasons, ["prioritario all'avvio", "correttivo dopo un errore"])
        finish.assert_not_awaited()

    async def test_without_a_fix_online_a_failed_update_still_rolls_back(self):
        reasons, _, finish = await self.boot(newer=set(), pipeline=False, pending={"from": "a", "to": "b"})
        self.assertEqual(reasons, ["prioritario all'avvio", "correttivo dopo un errore"])
        finish.assert_awaited_once_with(False)

    async def test_a_failed_optional_component_looks_for_a_fix_and_otherwise_continues(self):
        reasons, _, finish = await self.boot(newer=set(), failed_step="ollama")
        self.assertEqual(reasons, ["prioritario all'avvio", "correttivo per un componente non riuscito"])
        self.assertEqual(store.phase, "READY")

    async def test_a_failed_optional_component_takes_the_fix_when_one_exists(self):
        reasons, _, _ = await self.boot(newer={"componente"}, failed_step="ollama")
        self.assertEqual(reasons[-1], "correttivo per un componente non riuscito")
        self.assertNotEqual(store.phase, "READY")


class UpdaterPriorityTest(unittest.IsolatedAsyncioTestCase):
    async def test_disabling_auto_update_bypasses_every_online_check(self):
        with mock.patch("updater.DEMO", False), mock.patch("updater.env_get", return_value="0"), \
                mock.patch("updater.check", new_callable=mock.AsyncMock) as check:
            self.assertFalse(await updater.priority_update("prioritario all'avvio"))
        check.assert_not_awaited()

    async def test_a_newer_fix_keeps_the_original_rollback_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            pending_file = Path(tmp) / "update_pending.json"
            pending_file.write_text(json.dumps({"from": "good", "to": "broken", "at": 0}))
            info = {"available": True, "target_rev": "fixed", "local_rev": "broken"}
            with mock.patch("updater.PENDING_FILE", pending_file), \
                    mock.patch("updater.check", new_callable=mock.AsyncMock, return_value=info), \
                    mock.patch("updater.git", new_callable=mock.AsyncMock, return_value=(0, "")), \
                    mock.patch("updater.sh", new_callable=mock.AsyncMock, return_value=(0, "")), \
                    mock.patch("updater.asyncio.sleep", new_callable=mock.AsyncMock):
                self.assertTrue(await updater.apply("correttivo dopo un errore"))
            written = json.loads(pending_file.read_text())
        self.assertEqual((written["from"], written["to"]), ("good", "fixed"))


if __name__ == "__main__":
    unittest.main()
