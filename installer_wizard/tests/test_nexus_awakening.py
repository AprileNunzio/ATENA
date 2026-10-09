import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
from features.nexus import composition
from features.nexus.application.awakening_service import AwakeningService
from features.nexus.domain import awakening, summary
from features.nexus.infrastructure.json_store import JsonDocument

HEADERS = {"X-Atena-Request": "1"}
CATALOG = {"features": [
    {"id": "vision", "state": {"mode": "auto"}}, {"id": "ear", "state": {"mode": "0"}},
    {"id": "home_assistant", "state": {"mode": "auto"}, "values": {"HOME_ASSISTANT_URL": "http://ha:8123"}},
    {"id": "autonomy", "state": {"mode": "auto"}}, {"id": "agent", "state": {"mode": "1"}, "values": {"ATENA_AGENT_ACCESS": "standard"}},
]}


def service(path: Path, clock=lambda: 50.0) -> AwakeningService:
    return AwakeningService(JsonDocument(path), env=lambda: {"ATENA_USER_NAME": "Anna"}, catalog=lambda: CATALOG,
                            brain_mode=lambda: "local", clock=clock)


class AwakeningDomainTest(unittest.TestCase):
    def test_progress_and_next_step(self):
        self.assertEqual(awakening.progress({}), {"finished": 0, "total": 6, "percent": 0, "next": "language", "complete": False})
        marks = awakening.mark({}, "language", "done", "Anna", 1.0)
        marks = awakening.mark(marks, "level", "skipped", "", 2.0)
        self.assertEqual(awakening.progress(marks)["next"], "brain")
        for step in awakening.STEPS:
            marks = awakening.mark(marks, step, "done", "", 3.0)
        self.assertTrue(awakening.progress(marks)["complete"])

    def test_mark_rejects_bad_input(self):
        for step, status, note in (("hack", "done", ""), ("level", "maybe", ""), ("level", "done", 5)):
            with self.assertRaises(ValueError):
                awakening.mark({}, step, status, note, 0.0)
        self.assertEqual(len(awakening.mark({}, "level", "done", "x" * 500, 0.0)["level"].note), awakening.MAX_NOTE)

    def test_restore_and_trust_profiles(self):
        self.assertEqual(awakening.restore({"level": {"status": "done"}, "evil": {"status": "done"}, "home": {"status": "?"}}).keys(), {"level"})
        self.assertEqual(awakening.trust_profile("auto", "standard"), "balanced")
        self.assertEqual(awakening.trust_profile("1", "completo"), "autonomous")
        self.assertEqual(awakening.trust_profile("1", "standard"), "")

    def test_dashboard_reminds_unfinished_awakening(self):
        base = dict(phase="READY", progress=100.0, steps={}, step_titles={}, components={}, features=[], update={}, approvals=0)
        texts = [t.text for t in summary.todos(summary.Inputs(**base, awakening_left=1))]
        self.assertIn("Completa il Risveglio: manca 1 passo", texts)
        self.assertEqual(summary.todos(summary.Inputs(**base, awakening_left=0)), [])


class AwakeningServiceTest(unittest.TestCase):
    def test_state_reads_current_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = service(Path(tmp) / "a.json").state()
        current = state["current"]
        self.assertEqual(current["name"], "Anna")
        self.assertEqual(current["senses"], {"vision": "auto", "ear": "0"})
        self.assertTrue(current["home"]["connected"])
        self.assertEqual(current["trust"], "balanced")
        self.assertEqual([s["id"] for s in state["steps"]], list(awakening.STEPS))

    def test_mark_persists_privately_and_reset_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.json"
            svc = service(path)
            svc.mark({"step": "language", "status": "done", "note": "Anna · IT"})
            self.assertEqual(service(path).progress()["finished"], 1)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(svc.reset()["progress"]["finished"], 0)


class AwakeningApiTest(unittest.TestCase):
    def test_endpoints_require_session_and_validate(self):
        anon = TestClient(atena_supervisor.admin)
        self.assertEqual(anon.get("/api/nexus/awakening").status_code, 401)
        admin = TestClient(atena_supervisor.admin)
        admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        with mock.patch.object(composition.awakening, "document", JsonDocument(Path(tempfile.mkdtemp()) / "a.json")):
            self.assertEqual(admin.put("/api/nexus/awakening", json={"step": "level", "status": "done"}).status_code, 403)
            r = admin.put("/api/nexus/awakening", json={"step": "level", "status": "done", "note": "Pilota"}, headers=HEADERS)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["progress"]["finished"], 1)
            self.assertEqual(admin.put("/api/nexus/awakening", json={"step": "x", "status": "done"}, headers=HEADERS).status_code, 400)
            self.assertEqual(admin.get("/api/nexus/summary").json()["awakening"]["finished"], 1)
            self.assertEqual(admin.post("/api/nexus/awakening/reset", headers=HEADERS).json()["progress"]["finished"], 0)


if __name__ == "__main__":
    unittest.main()
