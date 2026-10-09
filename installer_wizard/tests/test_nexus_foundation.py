import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
from features.nexus import composition
from features.nexus.application.preferences_service import PreferencesService
from features.nexus.domain.preferences import MAX_FAVORITES, Preferences, amend, restore
from features.nexus.infrastructure.json_preferences import JsonPreferencesRepository

HEADERS = {"X-Atena-Request": "1"}
NEXUS = Path(__file__).resolve().parents[1] / "web" / "nexus"
IMPORT = re.compile(r'^\s*(?:import|export)\s[^"\']*?from\s+["\']([^"\']+)["\']', re.M)


class PreferencesDomainTest(unittest.TestCase):
    def test_defaults_and_invalid_storage_fall_back_safely(self):
        self.assertEqual(restore(None), Preferences())
        self.assertEqual(restore({"level": "root", "favorites": ["x"]}), Preferences())
        self.assertEqual(restore({"level": "architect", "favorites": ["vision", "vision"]}).favorites, ("vision",))

    def test_amend_validates_every_field(self):
        base = Preferences()
        self.assertEqual(amend(base, {"level": "explorer"}).level, "explorer")
        for bad in ({}, {"level": "god"}, {"favorites": "vision"}, {"favorites": ["../etc"]},
                    {"favorites": [f"t{i}" for i in range(MAX_FAVORITES + 1)]}, {"theme": "light"}, ["level"]):
            with self.assertRaises(ValueError, msg=bad):
                amend(base, bad)


class PreferencesRepositoryTest(unittest.TestCase):
    def test_round_trip_is_private_and_per_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nexus" / "prefs.json"
            service = PreferencesService(JsonPreferencesRepository(path))
            service.update("anna", {"level": "explorer", "favorites": ["chat"]})
            service.update("nunzio", {"level": "architect"})
            self.assertEqual(service.get("anna").as_dict(), {"level": "explorer", "favorites": ["chat"]})
            self.assertEqual(service.get("nunzio").level, "architect")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_rejects_unsafe_user_names(self):
        repo = JsonPreferencesRepository(Path(tempfile.mkdtemp()) / "p.json")
        for user in ("", "../x", "a b", "x" * 65):
            with self.assertRaises(ValueError):
                repo.save(user, {})


class NexusApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo_patch = mock.patch.object(composition.preferences, "repository",
                                           JsonPreferencesRepository(Path(cls.tmp.name) / "p.json"))
        cls.repo_patch.start()
        cls.admin = TestClient(atena_supervisor.admin)
        r = cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        assert r.status_code == 200, r.text

    @classmethod
    def tearDownClass(cls):
        cls.repo_patch.stop()
        cls.tmp.cleanup()

    def test_page_is_served_with_strict_security_headers(self):
        with mock.patch("setup_api.done", return_value=True):
            r = TestClient(atena_supervisor.admin).get("/nexus")
        self.assertEqual(r.status_code, 200)
        csp = r.headers["content-security-policy"]
        for directive in ("default-src 'none'", "script-src 'self'", "style-src 'self'", "frame-ancestors 'none'",
                          "object-src 'none'", "require-trusted-types-for 'script'"):
            self.assertIn(directive, csp)
        self.assertNotIn("unsafe", csp)
        self.assertEqual(r.headers["x-frame-options"], "DENY")
        self.assertEqual(r.headers["referrer-policy"], "no-referrer")
        self.assertIn("/static/nexus/app.js?v=", r.text)

    def test_page_redirects_to_setup_until_configured(self):
        with mock.patch("setup_api.done", return_value=False):
            r = TestClient(atena_supervisor.admin).get("/nexus", follow_redirects=False)
        self.assertEqual(r.status_code, 303)

    def test_preferences_require_a_session_and_the_request_header(self):
        anon = TestClient(atena_supervisor.admin)
        self.assertEqual(anon.get("/api/nexus/preferences").status_code, 401)
        self.assertEqual(self.admin.put("/api/nexus/preferences", json={"level": "pilot"}).status_code, 403)

    def test_preferences_round_trip_and_validation(self):
        r = self.admin.put("/api/nexus/preferences", json={"level": "architect", "favorites": ["vision"]}, headers=HEADERS)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.admin.get("/api/nexus/preferences").json(), {"level": "architect", "favorites": ["vision"]})
        self.assertEqual(self.admin.put("/api/nexus/preferences", json={"level": "x"}, headers=HEADERS).status_code, 400)
        self.assertEqual(self.admin.put("/api/nexus/preferences", content=b"[1]", headers=HEADERS).status_code, 400)
        big = json.dumps({"favorites": ["a" * 40] * 200}).encode()
        self.assertEqual(self.admin.put("/api/nexus/preferences", content=big, headers=HEADERS).status_code, 413)

    def test_static_assets_are_served(self):
        r = self.admin.get("/static/nexus/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r.headers["content-type"])


class NexusFrontendContractTest(unittest.TestCase):
    def test_index_has_no_inline_code(self):
        html = (NEXUS / "index.html").read_text(encoding="utf-8")
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)[^>]*>")
        self.assertNotIn("<style", html)
        self.assertNotRegex(html, r'\sstyle="')
        self.assertNotRegex(html, r"\son[a-z]+=")
        for ref in re.findall(r'(?:src|href)="/static/nexus/([^"?]+)"', html):
            self.assertTrue((NEXUS / ref).is_file(), ref)

    def test_every_module_import_resolves(self):
        for path in NEXUS.rglob("*.js"):
            for target in IMPORT.findall(path.read_text(encoding="utf-8")):
                self.assertTrue(target.startswith("."), f"{path.name}: import esterno {target}")
                self.assertTrue((path.parent / target).resolve().is_file(), f"{path.name} → {target}")

    def test_no_unsafe_dom_sinks(self):
        for path in NEXUS.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
                self.assertNotIn(sink, text, f"{path.name} usa {sink}")
            self.assertNotIn('setAttribute("style"', text, path.name)


if __name__ == "__main__":
    unittest.main()
