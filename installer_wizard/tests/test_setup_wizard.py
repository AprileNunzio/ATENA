import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient

import atena_supervisor
import setup_api
from config import read_env, write_env

HEADERS = {"X-Atena-Request": "1"}
BINARY = {**HEADERS, "Content-Type": "application/octet-stream"}
ONNX = b"\x08" + b"\x00" * 2048


class Network:
    def __init__(self, local: bool, private: bool = True):
        self.patches = [mock.patch.object(setup_api, "is_local", lambda r: local),
                        mock.patch.object(setup_api, "_private_client", lambda r: private or local)]

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()


class WizardTest(unittest.TestCase):
    def setUp(self):
        setup_api.SETUP_FILE.unlink(missing_ok=True)
        setup_api.guard.__init__()
        self.wake_dir = tempfile.TemporaryDirectory()
        self.wake = mock.patch.object(setup_api, "WAKE_DIR", Path(self.wake_dir.name))
        self.wake.start()
        self.public = TestClient(atena_supervisor.public)

    def tearDown(self):
        self.wake.stop()
        self.wake_dir.cleanup()
        setup_api.SETUP_FILE.unlink(missing_ok=True)

    def test_code_is_shown_only_on_the_device(self):
        with Network(local=True):
            self.assertEqual(self.public.get("/api/setup").json()["code"], setup_api.guard.code)
        with Network(local=False):
            data = self.public.get("/api/setup").json()
            self.assertTrue(data["needed"])
            self.assertIsNone(data["code"])
        with Network(local=False, private=False):
            self.assertEqual(self.public.get("/api/setup").status_code, 403)
            self.assertEqual(self.public.post("/api/setup", json={}, headers=HEADERS).status_code, 403)

    def test_remote_devices_need_the_code_and_get_locked_out(self):
        with Network(local=False):
            self.assertEqual(self.public.post("/api/setup/verify").status_code, 403)
            wrong = "000000" if setup_api.guard.code != "000000" else "111111"
            for _ in range(setup_api.MAX_ATTEMPTS):
                r = self.public.post("/api/setup/verify", headers={**HEADERS, "X-Atena-Setup-Code": wrong})
                self.assertEqual(r.status_code, 403)
            r = self.public.post("/api/setup/verify", headers={**HEADERS, "X-Atena-Setup-Code": setup_api.guard.code})
            self.assertEqual(r.status_code, 429)
            setup_api.guard.locked_until = 0
            r = self.public.post("/api/setup/verify", headers={**HEADERS, "X-Atena-Setup-Code": setup_api.guard.code})
            self.assertEqual(r.status_code, 200)

    def test_cross_site_requests_are_refused(self):
        with Network(local=True):
            r = self.public.post("/api/setup/verify", headers={**HEADERS, "Origin": "http://evil.example"})
            self.assertEqual(r.status_code, 403)

    def test_input_is_strictly_validated(self):
        for bad in ({"name": "Mario Rossi"}, {"name": "x;rm -rf /"}, {"lang": "de"}, {"profile": "enorme"},
                    {"voice": "../../etc"}, {"ha_url": "http://casa"}, {"ha_url": "javascript:alert(1)", "ha_token": "x" * 30},
                    {"telegram": "123:abc"}):
            with self.subTest(bad=bad), self.assertRaises(HTTPException):
                setup_api._clean(bad)
        out = setup_api._clean({"name": "Nunzio", "profile": "leggero", "commercial": "true"})
        self.assertEqual(out["ATENA_USER_NAME"], "Nunzio")
        self.assertEqual(out["ATENA_LLM_MODEL"], "granite3.3:2b")
        self.assertEqual(out["ATENA_VOICE"], "if_sara")
        self.assertEqual(out["ATENA_COMMERCIAL"], "0")

    def test_brain_choices(self):
        local = setup_api._clean({"brain": "local", "profile": "bilanciato"})
        self.assertEqual((local["ATENA_BRAIN"], local["ATENA_LLM_MODEL"]), ("local", "granite3.3:8b"))
        remote = setup_api._clean({"brain": "remote", "ollama_url": "192.168.1.30", "profile": "potente"})
        self.assertEqual(remote["ATENA_OLLAMA_URL"], "http://192.168.1.30:11434")
        self.assertNotIn("ATENA_LLM_MODEL", remote)
        cloud = setup_api._clean({"brain": "cloud", "cloud_provider": "anthropic", "cloud_key": "sk-ant-" + "a" * 40})
        self.assertEqual(cloud["ATENA_LLM_CHAT_ORDER"], "cloud:anthropic/claude-haiku-4-5-20251001")
        self.assertNotIn("sk-ant", " ".join(cloud.values()))
        for bad in ({"brain": "quantum"}, {"brain": "remote"}, {"brain": "remote", "ollama_url": "http://a b"},
                    {"brain": "cloud", "cloud_provider": "evil", "cloud_key": "x" * 30},
                    {"brain": "cloud", "cloud_provider": "gemini", "cloud_key": "short"},
                    {"brain": "cloud", "cloud_provider": "gemini", "cloud_key": "$(reboot)" * 5},
                    {"packages": ["voice", "rootkit"]}, {"packages": "voice"}):
            with self.subTest(bad=bad), self.assertRaises(HTTPException):
                setup_api._clean(bad)

    def test_only_the_chosen_packages_are_requested(self):
        out = setup_api._clean({"packages": ["voice", "documents"]})
        self.assertEqual(out["ATENA_VOICE_PACKAGE"], "1")
        self.assertEqual(out["ATENA_DOCUMENTS"], "1")
        self.assertNotIn("ATENA_EAR", out)
        self.assertNotIn("ATENA_VISION", out)

    def test_cloud_key_goes_to_the_vault_not_the_env_file(self):
        key = "AIza" + "b" * 35
        self.addCleanup(write_env, {"ATENA_BRAIN": "", "ATENA_LLM_CHAT_ORDER": "", "ATENA_LLM_DEEP_ORDER": ""})
        with Network(local=True), mock.patch("features.cloud.vault.vault.update") as update:
            r = self.public.post("/api/setup", json={"name": "Nunzio", "brain": "cloud", "cloud_provider": "gemini",
                                                     "cloud_key": key}, headers=HEADERS)
            self.assertEqual(r.status_code, 200, r.text)
        update.assert_called_once_with("gemini", {"key": key, "enabled": True})
        self.assertNotIn(key, "".join(read_env().values()))
        self.assertEqual(read_env().get("ATENA_BRAIN"), "cloud")
        self.assertEqual(r.json()["shares_password"], "")

    def test_the_owner_must_give_a_name(self):
        with Network(local=True):
            for body in ({}, {"name": ""}, {"name": "Nunzio", "last_name": "<script>"}, {"name": "Nunzio", "voice_lang": "xx"}):
                with self.subTest(body=body):
                    r = self.public.post("/api/setup", json=body, headers=HEADERS)
                    self.assertEqual(r.status_code, 400, r.text)
            self.assertFalse(setup_api.done())

    def test_completing_the_wizard_registers_the_owner_with_languages(self):
        from features.people import people
        with tempfile.TemporaryDirectory() as root, mock.patch.object(people, "PEOPLE_DIR", Path(root)), Network(local=False):
            r = self.public.post("/api/setup", json={"name": "Nunzio", "last_name": "D'Aprile", "lang": "fr",
                                                     "voice_lang": "en"}, headers={**HEADERS, "X-Atena-Setup-Code": setup_api.guard.code})
            self.assertEqual(r.status_code, 200, r.text)
            owner = people.load(r.json()["owner"])
            self.assertEqual((owner["role"], owner["first_name"], owner["last_name"]), ("owner", "Nunzio", "D'Aprile"))
            self.assertEqual((owner["ui_language"], owner["voice_language"]), ("fr", "en"))
            self.assertFalse(r.json()["voice_training"])
        self.addCleanup(write_env, {"ATENA_UI_LANG": "it"})

    def test_completing_the_wizard_closes_it(self):
        with Network(local=True):
            r = self.public.post("/api/setup", json={"name": "Nunzio", "lang": "it", "profile": "auto", "shares": True},
                                 headers=HEADERS)
            self.assertEqual(r.status_code, 200, r.text)
            password = r.json()["shares_password"]
            self.assertGreaterEqual(len(password), 20)
            self.assertEqual(read_env().get("ATENA_SMB_PASSWORD"), password)
            self.assertEqual(read_env().get("ATENA_USER_NAME"), "Nunzio")
            self.assertTrue(setup_api.done())
            self.assertEqual(os.stat(setup_api.SETUP_FILE).st_mode & 0o777, 0o600)
            self.assertFalse(self.public.get("/api/setup").json()["needed"])
            self.assertEqual(self.public.post("/api/setup", json={}, headers=HEADERS).status_code, 410)
            self.assertEqual(self.public.get("/setup", follow_redirects=False).status_code, 303)

    def test_wake_model_upload_checks_the_file(self):
        with Network(local=True):
            r = self.public.post("/api/setup/wakeword", content=ONNX, headers=BINARY)
            self.assertEqual(r.status_code, 200, r.text)
            target = Path(self.wake_dir.name) / "ehi_atena.onnx"
            self.assertEqual(target.read_bytes(), ONNX)
            self.assertEqual(os.stat(target).st_mode & 0o777, 0o644)
            self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ["ehi_atena.onnx"])
            for data, headers, status in ((b"\x08tiny", BINARY, 400), (b"#!" + ONNX, BINARY, 400),
                                          (ONNX, {**HEADERS, "Content-Type": "multipart/form-data"}, 415),
                                          (b"\x08" * (setup_api.WAKE_MAX_BYTES + 1), BINARY, 413)):
                with self.subTest(status=status, size=len(data)):
                    r = self.public.post("/api/setup/wakeword", content=data, headers=headers)
                    self.assertEqual(r.status_code, status)

    def test_answers_file_configures_a_headless_install(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "answers.env"
            path.write_text("ATENA_USER_NAME=Nunzio\nATENA_LLM_MODEL=granite3.3:8b\nATENA_EVIL=$(reboot)\n"
                            "ATENA_SMB_PASSWORD=Corretta-Batteria-42\n", encoding="utf-8")
            self.assertTrue(asyncio.run(setup_api.apply_answers_file(path)))
            self.assertFalse(path.exists())
            env = read_env()
            self.assertEqual(env.get("ATENA_LLM_MODEL"), "granite3.3:8b")
            self.assertEqual(env.get("ATENA_SMB_PASSWORD"), "Corretta-Batteria-42")
            self.assertEqual(env.get("ATENA_SHARES"), "1")
            self.assertNotIn("ATENA_EVIL", env)
            self.assertTrue(setup_api.done())

    def test_unsafe_answers_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            real = Path(root) / "real.env"
            real.write_text("ATENA_USER_NAME=Nunzio\n", encoding="utf-8")
            link = Path(root) / "answers.env"
            link.symlink_to(real)
            self.assertFalse(asyncio.run(setup_api.apply_answers_file(link)))
            bad = Path(root) / "bad.env"
            bad.write_text("ATENA_USER_NAME=Mario Rossi\n", encoding="utf-8")
            self.assertFalse(asyncio.run(setup_api.apply_answers_file(bad)))
            self.assertFalse(setup_api.done())

    def test_admin_can_upload_the_wake_model_after_setup(self):
        admin = TestClient(atena_supervisor.admin)
        self.assertEqual(admin.post("/api/setup/wakeword", content=ONNX, headers=BINARY).status_code, 401)
        admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        r = admin.post("/api/setup/wakeword", content=ONNX, headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(admin.post("/api/setup/wakeword", content=ONNX, headers=BINARY).status_code, 200)


if __name__ == "__main__":
    unittest.main()
