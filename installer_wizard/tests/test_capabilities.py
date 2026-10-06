import asyncio
import unittest
from unittest import mock

from features.agent import registry, tools_media
from features.capabilities import manifest
from features.cloud import conversation
from features.desktop.desk import desk
from features.music import commands
from features.music.outputs import Outputs
from state import store
from tests.test_music_library import Base


class ManifestTest(unittest.TestCase):
    def test_every_media_tool_is_known_to_the_agent_and_described_to_the_models(self):
        names = {t["name"] for t in manifest.tools()}
        self.assertTrue({"music_play", "music_search", "music_control", "music_outputs", "music_now", "open_camera", "close_camera", "list_cameras",
                         "show_widget", "list_widgets"} <= names)
        text = manifest.summary()
        for needle in ("metti AC DC", "Chromecast", "apri la webcam", "a tutto schermo", "music_play", "show_widget"):
            self.assertIn(needle, text)
        document = manifest.document()
        self.assertEqual(set(document), {"summary", "voice", "tools", "notes", "team"})
        self.assertTrue(all(t["description"] for t in document["tools"]))

    def test_the_prompt_of_cloud_models_carries_the_capabilities(self):
        prompt = conversation.persona({"capabilities": manifest.summary()})
        self.assertIn("COSA SAI FARE", prompt)
        self.assertNotIn("COSA SAI FARE", conversation.persona({}))


class MediaToolsTest(Base):
    def setUp(self):
        super().setUp()
        self.out = Outputs()
        for p in (mock.patch.object(commands, "outputs", self.out), mock.patch.object(tools_media, "outputs", self.out),
                  mock.patch.object(commands, "lan_base", return_value="http://192.168.1.2"),
                  mock.patch.object(self.out, "refresh", mock.AsyncMock(return_value=[{"id": "display:sala", "kind": "display", "name": "Sala", "active": False}]))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: setattr(store, "now_playing", {}))
        self.filled()
        self.out.remote_beat("display:sala", "Sala")

    def run_tool(self, tool_name: str, **args) -> str:
        return asyncio.run(registry.run(tool_name, args))

    def test_search_play_control_and_now_playing(self):
        self.assertIn("Luna", self.run_tool("music_search", query="luna"))
        self.assertIn("Sala", self.run_tool("music_outputs"))
        self.assertEqual(self.run_tool("music_now"), "non sta suonando nulla")
        self.assertIn("Sala", self.run_tool("music_play", query="la musica di Vasco", device="Sala"))
        self.assertIn("Sala", self.run_tool("music_now"))
        self.assertIn("40", self.run_tool("music_control", action="volume", value=40))
        self.assertEqual(self.out.sessions["display:sala"].volume, 0.4)
        self.assertEqual(self.run_tool("music_control", action="pause"), "in pausa")
        self.assertEqual(self.out.sessions["display:sala"].state, "paused")

    def test_errors_are_clear_for_the_model(self):
        with self.assertRaises(ValueError):
            self.run_tool("music_play", query="musica che non esiste affatto xyz")
        with self.assertRaises(ValueError):
            self.run_tool("music_play", query="luna", device="garage")
        with self.assertRaises(ValueError):
            self.run_tool("music_control", action="pause")
        self.run_tool("music_play", query="luna")
        with self.assertRaises(ValueError):
            self.run_tool("music_control", action="esplodi")

    def test_cameras_open_by_name_and_close(self):
        rows = [{"id": "w-1", "name": "Ingresso", "kind": "local", "device": "/dev/video0", "main": True, "ir": False},
                {"id": "w-2", "name": "Giardino", "kind": "local", "device": "/dev/video2", "main": False, "ir": False}]
        saved = dict(desk.instances)
        desk.scan()
        desk.instances.clear()
        self.addCleanup(lambda: (desk.instances.clear(), desk.instances.update(saved)))
        with mock.patch.object(tools_media.live, "listing", return_value=rows):
            with self.assertRaises(ValueError):
                self.run_tool("open_camera")
            self.assertIn("Giardino", self.run_tool("open_camera", name="giardino", fullscreen=True))
            self.assertIn("Giardino", self.run_tool("list_cameras"))
            self.assertIn("chiuse", self.run_tool("close_camera"))
            self.assertEqual(self.run_tool("close_camera"), "nessuna telecamera aperta")


if __name__ == "__main__":
    unittest.main()
