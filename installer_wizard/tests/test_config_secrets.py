import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
import system_api
from config import is_secret

HEADERS = {"X-Atena-Request": "1"}
COMPOSE = Path(__file__).resolve().parents[2] / "docker" / "docker-compose.yml"


class SecretKeysTest(unittest.TestCase):
    def test_secret_names_are_recognised(self):
        for key in ("ATENA_SECRET_KEY", "ATENA_GOOGLE_REFRESH_TOKEN", "ATENA_MUSIC_APP_PASSWORD", "ATENA_ONLINE_STT_KEY",
                    "OPENAI_API_KEY", "ATENA_SPOTIFY_CLIENT_SECRET", "ATENA_CLOUD_KEY"):
            self.assertTrue(is_secret(key), key)
        for key in ("ATENA_KIOSK", "ATENA_EMBED_MODEL", "ATENA_UI_LANG", "ATENA_WAKEWORD_SHA256", "ATENA_MACHINE"):
            self.assertFalse(is_secret(key), key)

    def test_config_never_returns_secret_values(self):
        admin = TestClient(atena_supervisor.admin)
        r = admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        self.assertEqual(r.status_code, 200, r.text)
        env = {"ATENA_SECRET_KEY": "a" * 64, "ATENA_GOOGLE_REFRESH_TOKEN": "refresh-secret-value",
               "ATENA_ONLINE_STT_KEY": "stt-secret-value-1234", "ATENA_MACHINE": "pi"}
        with mock.patch.object(system_api, "read_env", return_value=env):
            data = admin.get("/api/config", headers=HEADERS).json()
        text = str(data)
        for value in ("a" * 64, "refresh-secret-value", "stt-secret-value"):
            self.assertNotIn(value, text)
        self.assertEqual(data["system"]["ATENA_MACHINE"], "pi")
        self.assertEqual(data["system"]["ATENA_SECRET_KEY"], "••••")

    def test_gpu_inference_is_bound_to_loopback(self):
        self.assertIn('"127.0.0.1:8444:8444"', COMPOSE.read_text())


if __name__ == "__main__":
    unittest.main()
