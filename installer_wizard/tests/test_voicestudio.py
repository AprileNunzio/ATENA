import asyncio
import io
import json
import unittest
import wave
from unittest import mock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from access import require_admin
from features.voices import catalog, synthesis
from features.voicestudio import api as studio_api
from features.voicestudio import client as client_module
from features.voicestudio import design, tools
from features.voicestudio.client import StudioError, client, profile_of, safe_url


def tone(frames: int = 2400) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x01\x00" * frames)
    return out.getvalue()


class FakeStudio:
    def __init__(self, key: str = "secret") -> None:
        self.key = key
        self.profiles = {"ab12cd34": {"name": "Nonno Pino", "language": "it"}}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        if request.headers.get("authorization") != f"Bearer {self.key}":
            return httpx.Response(401, json={"detail": "unauthorized"})
        path = request.url.path
        if path == "/.well-known/voicestudio-speech":
            return httpx.Response(200, json={"protocol": "voicestudio.speech.v1"})
        if path == "/v1/audio/voices":
            voices = [{"voice_id": "alloy", "type": "openai_alias", "name": "Alloy"}]
            voices += [{"voice_id": k, "type": "profile", **v} for k, v in self.profiles.items()]
            return httpx.Response(200, json={"voices": voices})
        if path == "/v1/audio/speech":
            body = json.loads(request.content)
            if body["voice"] not in self.profiles:
                return httpx.Response(404, json={"detail": "voice not found"})
            return httpx.Response(200, content=tone(), headers={"content-type": "audio/wav"})
        if path == "/v1/audio/transcriptions":
            return httpx.Response(200, json={"text": "ciao a tutti"})
        if path == "/design/describe":
            text = json.loads(request.content)["description"]
            attrs = {"Gender": "female" if "female" in text else "Auto", "Age": "elderly" if "elderly" in text else "Auto"}
            return httpx.Response(200, json={"attrs": attrs})
        if path == "/profiles" and request.method == "POST":
            self.profiles["ee11ff22"] = {"name": "Nuova", "language": "it"}
            return httpx.Response(200, json={"id": "ee11ff22", "name": "Nuova"})
        if path.endswith("/consent"):
            return httpx.Response(200, json={"ok": True})
        if path.startswith("/profiles/") and request.method == "DELETE":
            self.profiles.pop(path.rsplit("/", 1)[1], None)
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"detail": "not found"})


ENV = {"ATENA_VOICESTUDIO": "1", "ATENA_VOICESTUDIO_WHERE": "local", "ATENA_VOICESTUDIO_KEY": "secret",
       "ATENA_VOICESTUDIO_URL": ""}


class StudioCase(unittest.TestCase):
    def setUp(self):
        self.fake = FakeStudio()
        self.saved = client.transport
        client.transport = httpx.MockTransport(self.fake)
        client.cached_at = 0.0
        self.env = dict(ENV)
        patcher = mock.patch.object(client_module, "env_get", side_effect=lambda k, d="": self.env.get(k, d))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        client.transport = self.saved
        client.cached, client.cached_at = [], 0.0


class AddressTest(unittest.TestCase):
    def test_only_home_network_addresses(self):
        self.assertEqual(safe_url("http://192.168.1.20:3900/"), "http://192.168.1.20:3900")
        self.assertEqual(safe_url("http://studio.local:3900"), "http://studio.local:3900")
        for bad in ("ftp://192.168.1.2", "http://8.8.8.8:3900", "http://example.com", "http://u:p@10.0.0.2",
                    "http://10.0.0.2/v1?x=1", ""):
            with self.subTest(bad=bad), self.assertRaises(StudioError):
                safe_url(bad)

    def test_voice_ids_are_validated(self):
        self.assertEqual(profile_of("studio_ab12cd34"), "ab12cd34")
        for bad in ("ab12cd34", "studio_../x", "studio_"):
            with self.subTest(bad=bad), self.assertRaises(StudioError):
                profile_of(bad)


class DesignTest(unittest.TestCase):
    def test_choices_become_a_description(self):
        self.assertEqual(design.describe({"gender": "female", "age": "elderly", "style": ""}), "female, elderly")
        with self.assertRaises(ValueError):
            design.describe({"gender": "robot"})
        with self.assertRaises(ValueError):
            design.describe({"style": ""})

    def test_consent_sentence_has_the_name(self):
        self.assertIn("Pino", design.sentence("it", "Pino"))
        self.assertIn("consent", design.sentence("xx-unknown", "Pino").replace("consenso", "consent"))
        self.assertEqual(design.filename("../../evil.sh"), "registrazione.webm")
        self.assertEqual(design.filename("voce.wav"), "registrazione.wav")


class ClientTest(StudioCase):
    def test_lists_only_profiles(self):
        voices = asyncio.run(client.voices())
        self.assertEqual([v["id"] for v in voices], ["studio_ab12cd34"])

    def test_wrong_key_is_explained(self):
        self.env["ATENA_VOICESTUDIO_KEY"] = "wrong"
        with self.assertRaisesRegex(StudioError, "chiave"):
            asyncio.run(client.voices())

    def test_atena_speaks_with_a_studio_voice(self):
        asyncio.run(client.voices())
        self.assertEqual(catalog.engine("studio_ab12cd34"), "studio")
        self.assertTrue(catalog.describe("studio_ab12cd34")["multi"])
        wav = asyncio.run(synthesis.speak_with("Ciao", "studio_ab12cd34", 1.0, "it"))
        self.assertTrue(wav.startswith(b"RIFF"))

    def test_design_needs_a_recognised_trait(self):
        with self.assertRaises(StudioError):
            asyncio.run(client.design("Robot", "metallic", "it"))
        self.assertEqual(asyncio.run(client.design("Nonna", "female, elderly", "it"))["id"], "ee11ff22")


class ToolsTest(StudioCase):
    def test_long_text_is_split_and_joined(self):
        parts = tools.chunks("Frase. " * 400)
        self.assertTrue(all(len(p) <= tools.CHUNK for p in parts))
        joined = tools.join_wavs([tone(100), tone(200)])
        with wave.open(io.BytesIO(joined)) as w:
            self.assertEqual(w.getnframes(), 300)

    def test_speak_to_file_saves_in_the_share(self):
        with mock.patch.object(catalog, "voice_name", return_value="af_sky"):
            result = asyncio.run(tools.speak_to_file(text="Uno. Due. Tre.", name="prova"))
        self.assertIn("Nonno Pino", result)
        path = result.split("audio salvato in ", 1)[1].split(" con la voce")[0]
        from pathlib import Path
        self.assertTrue(Path(path).read_bytes().startswith(b"RIFF"))
        Path(path).unlink()


class ApiTest(StudioCase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(studio_api.admin_routes)
        app.dependency_overrides[require_admin] = lambda: "nunzio"
        self.http = TestClient(app)
        self.written = {}
        patcher = mock.patch.object(studio_api, "write_env", side_effect=self.written.update)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_status_reports_voices_and_choices(self):
        data = self.http.get("/api/voicestudio").json()
        self.assertTrue(data["online"])
        self.assertEqual(data["voices"][0]["name"], "Nonno Pino")
        self.assertIn("gender", data["choices"])

    def test_status_when_off(self):
        self.env["ATENA_VOICESTUDIO"] = "0"
        data = self.http.get("/api/voicestudio").json()
        self.assertFalse(data["enabled"])
        self.assertEqual(self.fake.calls, [])

    def test_design_and_use(self):
        r = self.http.post("/api/voicestudio/design", json={"name": "Nonna", "gender": "female", "age": "elderly"})
        self.assertEqual(r.json()["voice"], "studio_ee11ff22")
        self.assertEqual(self.http.post("/api/voicestudio/design", json={"name": "<b>", "gender": "female"}).status_code, 400)
        with mock.patch.object(catalog, "custom_order", return_value=["if_sara"]):
            self.http.put("/api/voicestudio/use", json={"voice": "studio_ee11ff22"})
        self.assertEqual(self.written["ATENA_VOICE_ORDER"], "studio_ee11ff22,if_sara")
        self.assertEqual(self.http.put("/api/voicestudio/use", json={"voice": "studio_nope1234"}).status_code, 404)

    def test_clone_requires_consent_and_audio(self):
        audio = ("voce.webm", b"\x1a" * 30000, "audio/webm")
        r = self.http.post("/api/voicestudio/clone", data={"name": "Io", "consent": "0"}, files={"audio": audio})
        self.assertEqual(r.status_code, 400)
        r = self.http.post("/api/voicestudio/clone", data={"name": "Io", "consent": "1"},
                           files={"audio": ("x.sh", b"#!" * 20000, "text/x-sh")})
        self.assertEqual(r.status_code, 400)
        r = self.http.post("/api/voicestudio/clone", data={"name": "Io", "consent": "1"}, files={"audio": audio})
        self.assertEqual(r.json()["voice"], "studio_ee11ff22")
        self.assertIn(("POST", "/profiles/ee11ff22/consent"), self.fake.calls)

    def test_check_reports_problems_without_raising(self):
        r = self.http.post("/api/voicestudio/check", json={"url": "http://8.8.8.8:3900", "key": "x"}).json()
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
