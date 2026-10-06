import asyncio
import unittest
from unittest import mock

from fastapi.responses import Response
from fastapi.testclient import TestClient

import access
import atena_supervisor
from features.cameras import commands, live
from features.cameras.cameras import cameras
from features.desktop import desk as desk_module
from features.desktop.desk import desk
from features.vision.webcams import webcams

HEADERS = {"X-Atena-Request": "1"}


def device(name: str, node: str, bus: str, ir: bool = False) -> dict:
    return {"id": f"0c45:6366@{bus}", "name": name, "rgb": node, "ir": None, "has_ir": ir}


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = (webcams.state, dict(cameras.items), dict(desk.instances), dict(commands.pending))
        self.addCleanup(self.restore)
        desk.scan()
        desk.instances.clear()
        commands.pending["until"] = 0.0
        cameras.items = {}

    def restore(self):
        webcams.state, cameras.items, desk.instances, commands.pending = self.saved[0], self.saved[1], self.saved[2], self.saved[3]

    def webcams(self, *items):
        webcams.state = {"devices": list(items), "selected": {"rgb": items[0]["rgb"] if items else None}, "problems": []}

    def say(self, text: str):
        return asyncio.run(commands.answer(text))


class SourcesTest(Base):
    def test_listing_names_ids_and_main_device(self):
        self.webcams(device("HD Webcam", "/dev/video0", "usb-1"), device("CA20 Camera IR", "/dev/video2", "usb-2", True))
        rows = live.listing()
        self.assertEqual([r["name"] for r in rows], ["HD Webcam", "CA20 Camera IR"])
        self.assertEqual([r["main"] for r in rows], [True, False])
        self.assertTrue(all(live.find(r["id"]) for r in rows))
        self.assertEqual(len({r["id"] for r in rows}), 2)

    def test_identical_names_get_a_number_and_ip_cameras_hide_their_url(self):
        self.webcams(device("USB Camera", "/dev/video0", "usb-1"), device("USB Camera", "/dev/video4", "usb-2"))
        cameras.items = {"abcd1234": {"id": "abcd1234", "name": "Ingresso", "kind": "rtsp", "url": "rtsp://user:pass@10.0.0.9/stream", "created": 1},
                         "ffff0000": {"id": "ffff0000", "name": "Locale", "kind": "webcam", "url": "0", "created": 2}}
        names = [r["name"] for r in live.listing()]
        self.assertEqual(names, ["USB Camera", "USB Camera 2", "Ingresso"])
        public = live.public(live.listing())
        self.assertNotIn("pass", str(public))
        self.assertNotIn("device", public[0])

    def test_matching_by_name_position_and_infrared(self):
        self.webcams(device("HD Webcam", "/dev/video0", "usb-1"), device("CA20 Camera IR", "/dev/video2", "usb-2", True))
        cameras.items = {"abcd1234": {"id": "abcd1234", "name": "Salotto", "kind": "rtsp", "url": "rtsp://10.0.0.9/s", "created": 1}}
        rows = live.listing()
        self.assertEqual([r["name"] for r in live.match("la webcam salotto", rows)], ["Salotto"])
        self.assertEqual([r["name"] for r in live.match("la seconda", rows)], ["CA20 Camera IR"])
        self.assertEqual([r["name"] for r in live.match("quella a infrarossi", rows)], ["CA20 Camera IR"])
        self.assertEqual(live.match("apri la webcam", rows), [])
        self.assertEqual(live.match("cucina", rows), [])

    def test_ffmpeg_commands_for_each_kind_of_source(self):
        local = {"kind": "local", "device": "/dev/video2", "main": False}
        ip = {"kind": "ip", "device": "rtsp://10.0.0.9/s", "main": False}
        with mock.patch.object(live.shutil, "which", return_value="/usr/bin/ffmpeg"):
            command = live.ffmpeg_command(local, 8, 640)
            self.assertIn("v4l2", command)
            self.assertIn("/dev/video2", command)
            self.assertIn("mpjpeg", command)
            self.assertIn("fps=8,scale=640:-2", command)
            self.assertIn("tcp", live.ffmpeg_command(ip, 8, 640))
            self.assertIn("image2", live.ffmpeg_command(local, 8, 640, True))
        with mock.patch.object(live.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError):
                live.ffmpeg_command(local, 8, 640)


class VoiceTest(Base):
    def keys(self):
        return [k for k, i in desk.instances.items() if i["id"] == "live_cam"]

    def test_a_single_webcam_opens_without_a_name(self):
        self.webcams(device("HD Webcam", "/dev/video0", "usb-1"))
        speech, ui = self.say("apri la webcam")
        self.assertIn("HD Webcam", speech)
        self.assertEqual(len(self.keys()), 1)
        self.assertEqual(ui["mode"], "face")

    def test_several_devices_need_a_name_and_the_next_answer_picks_one(self):
        self.webcams(device("HD Webcam", "/dev/video0", "usb-1"), device("CA20 Camera IR", "/dev/video2", "usb-2", True))
        speech, _ = self.say("apri la telecamera")
        self.assertIn("Quale", speech)
        self.assertIn("CA20 Camera IR", speech)
        self.assertEqual(self.keys(), [])
        speech, _ = self.say("la seconda")
        self.assertIn("CA20 Camera IR", speech)
        self.assertEqual(len(self.keys()), 1)

    def test_a_name_in_the_sentence_and_fullscreen_in_one_go(self):
        self.webcams(device("HD Webcam", "/dev/video0", "usb-1"), device("CA20 Camera IR", "/dev/video2", "usb-2", True))
        speech, _ = self.say("apri la webcam HD a tutto schermo")
        self.assertIn("tutto schermo", speech)
        instance = desk.instances[self.keys()[0]]
        self.assertTrue(instance["fullscreen"])
        self.assertEqual(instance["data"]["name"], "HD Webcam")
        active = desk.active()
        self.assertTrue(active[0]["fullscreen"])

    def test_fullscreen_afterwards_and_back_to_normal(self):
        self.webcams(device("HD Webcam", "/dev/video0", "usb-1"))
        self.say("mostrami la webcam")
        key = self.keys()[0]
        self.assertFalse(desk.instances[key]["fullscreen"])
        self.say("mettila a tutto schermo")
        self.assertTrue(desk.instances[key]["fullscreen"])
        self.say("torna alla dimensione normale")
        self.assertFalse(desk.instances[key]["fullscreen"])

    def test_fullscreen_applies_to_any_widget_when_no_camera_is_open(self):
        desk.show("weather", {"x": 1})
        self.say("a tutto schermo")
        self.assertTrue(desk.instances["weather"]["fullscreen"])
        with self.assertRaises(LookupError):
            desk.instances.clear()
            self.say("a tutto schermo")

    def test_closing_one_or_all(self):
        self.webcams(device("HD Webcam", "/dev/video0", "usb-1"), device("CA20 Camera IR", "/dev/video2", "usb-2", True))
        self.say("apri tutte le telecamere")
        self.assertEqual(len(self.keys()), 2)
        speech, _ = self.say("chiudi la telecamera CA20")
        self.assertIn("CA20", speech)
        self.assertEqual(len(self.keys()), 1)
        self.say("chiudi la webcam")
        self.assertEqual(self.keys(), [])
        with self.assertRaises(LookupError):
            self.say("chiudi la webcam")

    def test_no_devices_and_unrelated_sentences(self):
        self.webcams()
        speech, _ = self.say("apri la webcam")
        self.assertIn("nessuna", speech)
        for text in ("che tempo fa", "accendi la luce", "scatta una foto"):
            with self.assertRaises(LookupError):
                self.say(text)

    def test_the_widget_is_a_valid_manifest(self):
        desk.scan()
        self.assertIn("live_cam", desk.widgets)
        self.assertFalse(desk.widgets["live_cam"]["personal"])


class ApiTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        assert cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS).status_code == 200
        cls.display = TestClient(atena_supervisor.public)

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(access, "is_local", lambda request: self.local)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.local = True
        self.webcams(device("HD Webcam", "/dev/video0", "usb-1"))

    def test_sources_stream_and_still_are_protected(self):
        source = live.listing()[0]["id"]
        self.assertEqual(self.display.get("/api/cameras/sources").json()["sources"][0]["name"], "HD Webcam")
        self.local = False
        for path in ("/api/cameras/sources", f"/api/cameras/live/{source}.mjpg", f"/api/cameras/live/{source}.jpg"):
            self.assertEqual(self.display.get(path).status_code, 401, path)
        self.assertEqual(self.admin.get("/api/cameras/sources", headers=HEADERS).status_code, 200)

    def test_unknown_or_malformed_sources_are_rejected(self):
        for source in ("w-deadbeef", "../etc", "x-12345678"):
            self.assertEqual(self.display.get(f"/api/cameras/live/{source}.jpg").status_code, 404, source)

    def test_stream_and_still_use_the_source(self):
        source = live.listing()[0]
        with mock.patch.object(live, "stream", mock.AsyncMock(return_value=Response(b"x", media_type="multipart/x-mixed-replace; boundary=frame"))):
            self.assertEqual(self.display.get(f"/api/cameras/live/{source['id']}.mjpg").status_code, 200)
        with mock.patch.object(live, "snapshot_bytes", mock.AsyncMock(return_value=b"\xff\xd8jpeg")):
            r = self.display.get(f"/api/cameras/live/{source['id']}.jpg")
            self.assertEqual((r.status_code, r.headers["content-type"]), (200, "image/jpeg"))
        with mock.patch.object(live, "snapshot_bytes", mock.AsyncMock(return_value=None)):
            self.assertEqual(self.display.get(f"/api/cameras/live/{source['id']}.jpg").status_code, 503)

    def test_display_can_toggle_fullscreen_and_close(self):
        desk.scan()
        desk.show("live_cam", {"source": "w-1", "name": "x"}, key="live:w-1")
        self.assertEqual(self.display.post("/api/desk/fullscreen", json={"key": "live:w-1", "on": True}).status_code, 200)
        self.assertTrue(desk.instances["live:w-1"]["fullscreen"])
        self.assertEqual(self.display.post("/api/desk/fullscreen", json={"key": "nulla"}).status_code, 404)
        self.assertEqual(self.display.post("/api/desk/close", json={"key": "live:w-1"}).status_code, 200)
        self.assertNotIn("live:w-1", desk.instances)
        self.local = False
        self.assertEqual(self.display.post("/api/desk/close", json={"key": "x"}).status_code, 401)

    def test_module_sanity(self):
        self.assertIs(desk_module.desk, desk)


if __name__ == "__main__":
    unittest.main()
