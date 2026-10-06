import http.client
import json
import threading
import unittest
from http import HTTPStatus
from unittest import mock

import safe_mode


class ClassifyTest(unittest.TestCase):
    def test_missing_third_party_library(self):
        self.assertEqual(safe_mode.classify(ModuleNotFoundError("x", name="uvicorn")), "missing_library")

    def test_broken_local_module(self):
        self.assertEqual(safe_mode.classify(ModuleNotFoundError("x", name="features.brain")), "broken_code")
        self.assertEqual(safe_mode.classify(ImportError("x", name="config")), "broken_code")
        self.assertEqual(safe_mode.classify(SyntaxError("bad")), "broken_code")

    def test_system_and_unknown(self):
        self.assertEqual(safe_mode.classify(PermissionError("denied")), "system")
        self.assertEqual(safe_mode.classify(RuntimeError("boom")), "unknown")

    def test_description_hides_install_path(self):
        text = safe_mode.describe(OSError(f"{safe_mode.ATENA_DIR}/x missing"))
        self.assertNotIn(str(safe_mode.ATENA_DIR), text)


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = safe_mode.SafeState("missing_library", "ModuleNotFoundError: No module named 'uvicorn'")
        cls.servers = safe_mode.serve(cls.state, (0, 0))
        cls.thread = threading.Thread(target=cls.servers[0].serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.servers[0].server_address[1]

    @classmethod
    def tearDownClass(cls):
        for server in cls.servers:
            server.shutdown()
            server.server_close()

    def setUp(self):
        safe_mode._last_request = 0.0

    def request(self, method, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, headers=headers or {})
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp, body

    def test_health_reports_safe_mode(self):
        resp, body = self.request("GET", "/healthz")
        self.assertEqual(resp.status, 200)
        self.assertEqual(json.loads(body), {"ok": True, "safe_mode": True, "reason": "missing_library"})

    def test_state_snapshot(self):
        _, body = self.request("GET", "/api/safe")
        data = json.loads(body)
        self.assertTrue(data["safe_mode"])
        self.assertEqual(data["reason"], "missing_library")

    def test_page_is_locked_down(self):
        resp, body = self.request("GET", "/")
        csp = resp.getheader("Content-Security-Policy")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("script-src 'sha256-", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertEqual(resp.getheader("X-Frame-Options"), "DENY")
        self.assertIn(b"api/safe/repair", body)

    def test_other_apis_are_unavailable(self):
        resp, _ = self.request("GET", "/api/state")
        self.assertEqual(resp.status, 503)

    def test_repair_requires_local_header_and_origin(self):
        with mock.patch.object(safe_mode, "start_repair", return_value=True) as start:
            resp, _ = self.request("POST", "/api/safe/repair")
            self.assertEqual(resp.status, 403)
            resp, _ = self.request("POST", "/api/safe/repair", {"X-Atena-Request": "1", "Origin": "http://evil.example"})
            self.assertEqual(resp.status, 403)
            start.assert_not_called()

    def test_repair_is_rate_limited(self):
        headers = {"X-Atena-Request": "1", "Origin": f"http://127.0.0.1:{self.port}"}
        with mock.patch.object(safe_mode, "start_repair", return_value=True) as start, \
                mock.patch.object(safe_mode, "repair_running", return_value=False):
            resp, _ = self.request("POST", "/api/safe/repair", headers)
            self.assertEqual(resp.status, HTTPStatus.ACCEPTED)
            resp, _ = self.request("POST", "/api/safe/repair", headers)
            self.assertEqual(resp.status, HTTPStatus.TOO_MANY_REQUESTS)
            self.assertEqual(start.call_count, 1)

    def test_repair_conflicts_while_running(self):
        with mock.patch.object(safe_mode, "repair_running", return_value=True):
            resp, _ = self.request("POST", "/api/safe/repair", {"X-Atena-Request": "1"})
            self.assertEqual(resp.status, HTTPStatus.CONFLICT)

    def test_unsupported_methods(self):
        resp, _ = self.request("DELETE", "/api/safe/repair")
        self.assertEqual(resp.status, 405)


class LaunchTest(unittest.TestCase):
    def test_import_failure_enters_safe_mode(self):
        import atena_launch

        failing = ModuleNotFoundError("No module named 'uvicorn'", name="uvicorn")
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "atena_supervisor":
                raise failing
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import), \
                mock.patch.object(safe_mode, "run") as run, \
                self.assertLogs("atena.launch", level="ERROR"):
            atena_launch.main()
        run.assert_called_once_with(failing)


if __name__ == "__main__":
    unittest.main()
