import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
import packages
from state import store

HEADERS = {"X-Atena-Request": "1"}
P = packages.PACKAGE_BY_ID


class PackageRulesTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: dict(v) for k, v in store.steps.items()}
        for sid in packages.PACKAGE_BY_STEP:
            store.steps.pop(sid, None)
        self.addCleanup(self.restore)

    def restore(self):
        store.steps.clear()
        store.steps.update(self.saved)

    def test_optional_packages_wait_for_a_request(self):
        env = {}
        for pid in ("voice", "ear", "documents", "convert3d", "sandbox", "shares", "native", "music"):
            with self.subTest(pid=pid):
                self.assertFalse(packages.wanted(P[pid], env))
                for sid in P[pid].steps:
                    self.assertFalse(packages.step_wanted(sid, env))

    def test_core_steps_are_never_gated(self):
        for sid in ("preflight", "system", "docker", "security", "core", "services", "maintenance"):
            self.assertTrue(packages.step_wanted(sid, {}))

    def test_explicit_request_and_removal(self):
        self.assertTrue(packages.wanted(P["documents"], {"ATENA_DOCUMENTS": "1"}))
        self.assertFalse(packages.wanted(P["documents"], {"ATENA_DOCUMENTS": "0"}))
        self.assertTrue(packages.wanted(P["convert3d"], {"ATENA_3D_CONVERT": "auto"}))

    def test_installed_steps_keep_converging_so_removal_can_disable_them(self):
        store.steps["vision"] = {"status": "done"}
        self.assertTrue(packages.step_wanted("vision", {"ATENA_VISION": "0"}))

    def test_brain_modes(self):
        cases = {"local": (True, True), "remote": (False, True), "cloud": (False, False)}
        for mode, (local, models) in cases.items():
            with self.subTest(mode=mode):
                env = {"ATENA_BRAIN": mode}
                self.assertEqual(packages.step_wanted("ollama", env), local)
                self.assertEqual(packages.step_wanted("brain", env), local)
                self.assertEqual(packages.step_wanted("models", env), models)
                self.assertEqual(packages.step_wanted("warmup", env), models)

    def test_brain_mode_detects_a_remote_server(self):
        with mock.patch.object(packages, "DEMO", False), mock.patch.object(packages, "ollama_remote", return_value=True):
            self.assertEqual(packages.brain_mode({}), "remote")
        with mock.patch.object(packages, "DEMO", False), mock.patch.object(packages, "ollama_remote", return_value=False), \
                mock.patch.object(packages.shutil, "which", return_value=None):
            self.assertEqual(packages.brain_mode({}), "pending")

    def test_non_removable_packages_cannot_be_turned_off(self):
        with self.assertRaises(KeyError):
            packages.request_updates("voice", False)
        with self.assertRaises(KeyError):
            packages.request_updates("brain_models", True)
        self.assertEqual(packages.request_updates("documents", True), {"ATENA_DOCUMENTS": "1"})
        self.assertEqual(packages.request_updates("brain_local", True), {"ATENA_BRAIN": "local"})


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: dict(v) for k, v in store.steps.items()}
        for sid in packages.PACKAGE_BY_STEP:
            store.steps.pop(sid, None)
        self.addCleanup(lambda: (store.steps.clear(), store.steps.update(self.saved)))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.mark = mock.patch.object(packages, "MARK_FILE", Path(tmp.name) / "packages.json")
        self.mark.start()
        self.addCleanup(self.mark.stop)
        self.env = {}
        for target in (mock.patch.object(packages, "read_env", lambda: dict(self.env)),
                       mock.patch.object(packages, "write_env", self.env.update),
                       mock.patch.object(packages, "ollama_remote", return_value=False)):
            target.start()
            self.addCleanup(target.stop)

    def test_existing_installs_keep_everything_they_had(self):
        for sid in ("office", "vision", "ollama", "models"):
            store.steps[sid] = {"status": "done"}
        self.env["ATENA_VISION"] = "0"
        updates = packages.migrate()
        self.assertEqual(updates, {"ATENA_DOCUMENTS": "1", "ATENA_BRAIN": "local"})
        self.assertEqual(self.env["ATENA_VISION"], "0")
        self.assertEqual(packages.migrate(), {})

    def test_fresh_installs_write_nothing(self):
        self.assertEqual(packages.migrate(), {})
        self.assertEqual(self.env, {})
        self.assertTrue(packages.MARK_FILE.exists())


class HealthAndChatTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: dict(v) for k, v in store.steps.items()}
        for sid in packages.PACKAGE_BY_STEP:
            store.steps.pop(sid, None)
        self.addCleanup(lambda: (store.steps.clear(), store.steps.update(self.saved)))

    def test_components_not_requested_are_shown_on_demand(self):
        import health
        down = {"status": "down", "detail": "Non raggiungibile"}
        results = {k: dict(down) for k in ("ollama", "llm", "voice", "vision", "ear", "kiosk", "core")}
        with mock.patch.object(packages, "_detect", return_value=False):
            out = health.on_demand(results, {"ATENA_BRAIN": "cloud", "ATENA_EAR": "1"})
        for key in ("ollama", "llm", "voice", "vision", "kiosk"):
            self.assertTrue(out[key].get("on_demand"), key)
            self.assertEqual(out[key]["status"], "ok")
        self.assertEqual(out["ear"], down)
        self.assertEqual(out["core"], down)

    def test_chat_can_install_a_package(self):
        import asyncio
        from features.agent import registry, tools_packages
        self.assertTrue(registry.needs_confirm("packages", {"action": "install"}))
        self.assertFalse(registry.needs_confirm("packages", {"action": "list"}))
        with mock.patch("settings.apply_config", return_value=["office"]) as apply, \
                mock.patch.object(packages, "read_env", return_value={}):
            out = asyncio.run(tools_packages.manage("install", "Documenti Office"))
        self.assertIn("avviata", out)
        self.assertEqual(apply.call_args.args[0], {"ATENA_DOCUMENTS": "1"})
        with self.assertRaises(ValueError):
            asyncio.run(tools_packages.manage("install", "niente"))
        self.assertIn("non si può", asyncio.run(tools_packages.manage("remove", "voice")))


class PackagesApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        r = cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        assert r.status_code == 200, r.text

    def test_listing(self):
        data = self.admin.get("/api/packages", headers=HEADERS).json()
        ids = {p["id"] for p in data["packages"]}
        self.assertIn("documents", ids)
        self.assertNotIn("brain_models", ids)
        self.assertIn(data["brain"], ("local", "remote", "cloud", "pending"))

    def test_request_installs_through_the_configuration(self):
        with mock.patch("packages_api.apply_config", return_value=["office"]) as apply:
            r = self.admin.post("/api/packages/documents", json={"on": True}, headers=HEADERS)
        self.assertEqual(r.status_code, 200, r.text)
        apply.assert_called_once()
        self.assertEqual(apply.call_args.args[0], {"ATENA_DOCUMENTS": "1"})
        self.assertEqual(apply.call_args.args[2], ["office"])

    def test_unknown_or_locked_packages(self):
        self.assertEqual(self.admin.post("/api/packages/nope", json={"on": True}, headers=HEADERS).status_code, 404)
        self.assertEqual(self.admin.post("/api/packages/voice", json={"on": False}, headers=HEADERS).status_code, 404)

    def test_brain_choice(self):
        with mock.patch("packages_api.apply_config", return_value=[]) as apply:
            r = self.admin.post("/api/packages/brain", json={"mode": "remote", "url": "192.168.1.20"}, headers=HEADERS)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(apply.call_args.args[0], {"ATENA_BRAIN": "remote", "ATENA_OLLAMA_URL": "http://192.168.1.20:11434"})
            self.assertEqual(apply.call_args.args[2], ["models", "warmup"])
            self.assertEqual(self.admin.post("/api/packages/brain", json={"mode": "remote"}, headers=HEADERS).status_code, 400)
            self.assertEqual(self.admin.post("/api/packages/brain", json={"mode": "x"}, headers=HEADERS).status_code, 400)

    def test_requires_admin(self):
        anon = TestClient(atena_supervisor.admin)
        self.assertEqual(anon.get("/api/packages").status_code, 401)
        self.assertEqual(self.admin.post("/api/packages/documents", json={"on": True}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
