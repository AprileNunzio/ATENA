import unittest
from unittest import mock

from fastapi.testclient import TestClient

import access
import atena_supervisor

HEADERS = {"X-Atena-Request": "1"}


class GovernorApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        r = cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        assert r.status_code == 200, r.text
        cls.display = TestClient(atena_supervisor.public)
        cls.stranger = TestClient(atena_supervisor.public)

    def setUp(self):
        self.local = mock.patch.object(access, "is_local", lambda request: self.client_is_local)
        self.local.start()
        self.addCleanup(self.local.stop)
        self.client_is_local = False

    def test_admin_views(self):
        for path in ("/api/governor/state", "/api/governor/history", "/api/scheduler/state", "/api/ear/review"):
            with self.subTest(path=path):
                r = self.admin.get(path, headers=HEADERS)
                self.assertEqual(r.status_code, 200, r.text[:300])
        state = self.admin.get("/api/governor/state", headers=HEADERS).json()
        for key in ("hardware", "class", "slots", "policy", "top", "thresholds"):
            self.assertIn(key, state)
        scheduler = self.admin.get("/api/scheduler/state", headers=HEADERS).json()
        self.assertIn("loops", scheduler)
        self.assertIn("upcoming", scheduler)

    def test_admin_views_require_login(self):
        anon = TestClient(atena_supervisor.admin)
        for path in ("/api/governor/state", "/api/scheduler/state", "/api/ear/review"):
            with self.subTest(path=path):
                self.assertEqual(anon.get(path, headers=HEADERS).status_code, 401)
        self.assertEqual(anon.post("/api/ear/review/purge", headers=HEADERS).status_code, 401)
        self.assertEqual(anon.post("/api/governor/reset", headers=HEADERS).status_code, 401)

    def test_policy_and_report_only_for_the_display(self):
        self.assertEqual(self.stranger.get("/api/governor/policy").status_code, 401)
        self.assertEqual(self.stranger.post("/api/governor/report", json={"device": "abcdef12"}).status_code, 401)
        self.client_is_local = True
        policy = self.display.get("/api/governor/policy", params={"device": "abcdef12"}).json()
        for key in ("class", "tier", "max_active", "max_ambient", "report"):
            self.assertIn(key, policy)

    def test_report_is_validated(self):
        self.client_is_local = True
        self.assertEqual(self.display.post("/api/governor/report", json={"device": "x"}).status_code, 400)
        self.assertEqual(self.display.post("/api/governor/report", content=b"{no").status_code, 400)
        self.assertEqual(self.display.post("/api/governor/report", content=b"x" * 40000).status_code, 413)
        ok = self.display.post("/api/governor/report", json={"device": "apitest01", "fps": 30, "p95": 20, "active": 2,
                                                              "widgets": [{"id": "meteo", "ms": 4, "nodes": 120}]})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertIn("tier", ok.json())

    def test_mic_config_for_the_display(self):
        self.assertEqual(self.stranger.get("/api/ear/config").status_code, 401)
        self.client_is_local = True
        config = self.display.get("/api/ear/config").json()
        self.assertEqual(set(config), {"echoCancellation", "noiseSuppression", "autoGainControl"})
        self.assertTrue(config["echoCancellation"])
        self.assertFalse(config["noiseSuppression"])

    def test_cron_automation_round_trip(self):
        spec = {"name": "Cron CI", "triggers": [{"type": "cron", "expr": "*/5 * * * *"}], "actions": [{"type": "log", "text": "x"}]}
        created = self.admin.post("/api/automations", json=spec, headers=HEADERS)
        self.assertEqual(created.status_code, 200, created.text)
        aid = created.json()["id"]
        upcoming = self.admin.get("/api/scheduler/state", headers=HEADERS).json()["upcoming"]
        self.assertTrue(any(row["id"] == aid for row in upcoming))
        bad = self.admin.post("/api/automations", json={**spec, "triggers": [{"type": "cron", "expr": "99 * * * *"}]}, headers=HEADERS)
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.admin.delete(f"/api/automations/{aid}", headers=HEADERS).status_code, 200)


if __name__ == "__main__":
    unittest.main()
