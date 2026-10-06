import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from fastapi.testclient import TestClient

import access
import atena_supervisor
from features.cameras import captures, controls, discovery, events, live, motion, netguard, options, presets, probe, unified
from features.cameras.cameras import cameras
from features.vision.webcams import webcams

HEADERS = {"X-Atena-Request": "1"}
LIST_CTRLS = """
                     brightness 0x00980900 (int)    : min=0 max=255 step=1 default=128 value=100
                       contrast 0x00980901 (int)    : min=0 max=255 step=1 default=32 value=32
            white_balance_automatic 0x0098090c (bool)   : default=1 value=1
        power_line_frequency 0x00980918 (menu)   : min=0 max=2 default=2 value=2
				0: Disabled
				1: 50 Hz
				2: 60 Hz
              exposure_absolute 0x009a0902 (int)    : min=3 max=2047 step=1 default=250 value=250 flags=inactive
"""


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="cam-"))
        for target, value in ((options, "FILE"), (captures, "PHOTOS"), (captures, "CAM_DIR")):
            patcher = mock.patch.object(target, value, self.dir / (value.lower() if value != "FILE" else "options.json"))
            patcher.start()
            self.addCleanup(patcher.stop)
        events.clear()
        self.saved = (webcams.state, dict(cameras.items))
        self.addCleanup(self.restore)
        cameras.items = {}

    def restore(self):
        webcams.state, cameras.items = self.saved[0], self.saved[1]

    def webcams(self, *items, main="/dev/video0"):
        webcams.state = {"devices": list(items), "selected": {"rgb": main, "ir": None}, "problems": []}


def device(name, rgb, ir=None, bus="usb-1"):
    return {"id": f"0c45:6366@{bus}", "name": name, "rgb": rgb, "ir": ir, "has_ir": bool(ir)}


class OptionsTest(Temp):
    def test_validation_clamps_and_cleans(self):
        saved = options.put("w-12345678", {"alias": "  Salotto   grande ", "rotate": 91, "fps": 1, "width": 700, "sensitivity": 99, "motion": True})
        self.assertEqual((saved["alias"], saved["rotate"], saved["fps"], saved["width"], saved["sensitivity"]), ("Salotto grande", 0, 2, 0, 10))
        self.assertTrue(options.get("w-12345678")["motion"])

    def test_invalid_source_and_bad_controls_rejected(self):
        with self.assertRaises(ValueError):
            options.put("../etc", {})
        saved = options.put("c-abcdef12", {"controls": {"brightness": 5, "Bad Name": 3, "x": True, "contrast": "9"}})
        self.assertEqual(saved["controls"], {"brightness": 5})

    def test_filters_order(self):
        self.assertEqual(options.filters({"rotate": 90, "mirror": True}), ["transpose=1", "hflip"])
        self.assertEqual(options.filters({"rotate": 0, "mirror": False}), [])

    def test_alias_and_hidden_reach_listing_and_voice(self):
        self.webcams(device("HD Webcam", "/dev/video0", "/dev/video2"))
        sid = live.local_id(device("HD Webcam", "/dev/video0"))
        options.put(sid, {"alias": "Scrivania", "room": "studio"})
        self.assertEqual([r["name"] for r in live.listing()], ["Scrivania"])
        self.assertEqual(len(live.all_rows()), 2)
        options.put(sid, {"hidden": True})
        self.assertEqual(live.listing(), [])
        self.assertEqual(len(live.all_rows()), 2)

    def test_ffmpeg_command_uses_overrides(self):
        with mock.patch.object(live.shutil, "which", return_value="/usr/bin/ffmpeg"):
            options.put("c-abcdef12", {"rotate": 90, "mirror": True, "fps": 12, "width": 960})
            command = live.ffmpeg_command({"id": "c-abcdef12", "kind": "ip", "device": "rtsp://10.0.0.5/s"}, 8, 640)
        self.assertIn("transpose=1,hflip,fps=12,scale=960:-2", command)


class NetworkTest(unittest.TestCase):
    def test_private_hosts_only(self):
        self.assertTrue(netguard.private_address("192.168.1.5"))
        self.assertTrue(netguard.private_address("127.0.0.1"))
        self.assertFalse(netguard.private_address("8.8.8.8"))
        self.assertFalse(netguard.lan_url("rtsp://8.8.8.8/stream"))
        self.assertTrue(netguard.lan_url("rtsp://192.168.1.50:554/stream"))
        self.assertFalse(netguard.lan_url("file:///etc/passwd"))
        self.assertFalse(netguard.lan_url("rtsp://bad host/x"))

    def test_redact_hides_credentials(self):
        text = netguard.redact("error opening rtsp://admin:secret@10.0.0.2/x", "rtsp://admin:secret@10.0.0.2/x")
        self.assertNotIn("secret", text)
        self.assertNotIn("admin", netguard.redact("fail rtsp://admin:secret@10.0.0.2/x"))

    def test_discovery_network_limits(self):
        self.assertEqual(str(discovery.network_for("192.168.1.7/24")), "192.168.1.0/24")
        for bad in ("8.8.8.0/24", "10.0.0.0/16", "127.0.0.0/24"):
            with self.assertRaises(ValueError):
                discovery.network_for(bad)

    def test_parse_onvif_reply(self):
        reply = b"<d:XAddrs>http://192.168.1.60:80/onvif/device_service</d:XAddrs><d:Scopes>onvif://www.onvif.org/name/Cam%20Ingresso</d:Scopes>"
        self.assertEqual(discovery.parse_onvif(reply)["host"], "192.168.1.60")
        self.assertEqual(discovery.parse_onvif(reply)["name"], "Cam Ingresso")
        self.assertIsNone(discovery.parse_onvif(b"<d:XAddrs>http://8.8.8.8/onvif</d:XAddrs>"))

    def test_scan_collects_open_ports(self):
        async def fake(host, port, gate):
            return host.endswith(".5") and port == 554
        with mock.patch.object(discovery, "port_open", fake):
            found = asyncio.run(discovery.scan(discovery.network_for("192.168.7.0/28")))
        self.assertEqual(found, {"192.168.7.5": [554]})


class PresetTest(unittest.TestCase):
    def test_brand_urls(self):
        self.assertEqual(presets.build("hikvision", "10.0.0.5", "admin", "p@ss", 2, "sub"), "rtsp://admin:p%40ss@10.0.0.5:554/Streaming/Channels/202")
        self.assertEqual(presets.build("reolink", "10.0.0.5", "", "", 1, "main"), "rtsp://10.0.0.5:554/h264Preview_01_main")
        self.assertIn("channel=3&subtype=1", presets.build("dahua", "10.0.0.5", "u", "p", 3, "sub"))

    def test_rejects_bad_input(self):
        for args in (("nope", "10.0.0.5"), ("hikvision", "bad host!")):
            with self.assertRaises(ValueError):
                presets.build(*args)
        with self.assertRaises(ValueError):
            presets.build("hikvision", "10.0.0.5", port=70000)


class ProbeTest(unittest.TestCase):
    def test_jpeg_size_and_hints(self):
        jpeg = b"\xff\xd8" + b"\xff\xc0\x00\x11\x08" + (360).to_bytes(2, "big") + (640).to_bytes(2, "big") + b"\x03" + b"\x00" * 20
        self.assertEqual(probe.jpeg_size(jpeg), (640, 360))
        self.assertIn("password", probe.hint("401 Unauthorized"))
        self.assertIn("Percorso", probe.hint("404 Not Found"))

    def test_refuses_public_addresses_and_reports_success(self):
        self.assertFalse(asyncio.run(probe.test("rtsp://8.8.8.8/x"))["ok"])
        jpeg = b"\xff\xd8\xff\xc0\x00\x11\x08" + (480).to_bytes(2, "big") + (848).to_bytes(2, "big") + b"\x03" + b"\x00" * 20
        with mock.patch.object(probe, "grab", return_value=(jpeg, "")), mock.patch.object(netguard, "lan_url", return_value=True):
            result = asyncio.run(probe.test("rtsp://192.168.1.9/x"))
        self.assertTrue(result["ok"])
        self.assertEqual((result["width"], result["height"]), (848, 480))


class ControlsTest(unittest.TestCase):
    def test_parse_all_kinds(self):
        rows = {r["name"]: r for r in controls.parse(LIST_CTRLS)}
        self.assertEqual(rows["brightness"]["value"], 100)
        self.assertEqual(rows["white_balance_automatic"]["type"], "bool")
        self.assertEqual([m["value"] for m in rows["power_line_frequency"]["menu"]], [0, 1, 2])
        self.assertTrue(rows["exposure_absolute"]["inactive"])

    def test_check_enforces_limits(self):
        row = controls.parse(LIST_CTRLS)[0]
        self.assertEqual(controls.check(row, 200), 200)
        for bad in (300, -1, True, "5"):
            with self.assertRaises(ValueError):
                controls.check(row, bad)

    def test_apply_unknown_control_and_node_guard(self):
        with mock.patch.object(controls, "read", return_value=controls.parse(LIST_CTRLS)):
            with self.assertRaises(ValueError):
                controls.apply("/dev/video0", "rm -rf", 1)
        with self.assertRaises(ValueError):
            controls.node_of({"node": "/dev/video9; ls"})

    def test_apply_writes_valid_value(self):
        calls = []
        with mock.patch.object(controls, "read", return_value=controls.parse(LIST_CTRLS)), mock.patch.object(controls, "write", lambda *a: calls.append(a)):
            controls.apply("/dev/video0", "contrast", 40)
        self.assertEqual(calls, [("/dev/video0", "contrast", 40)])


class CapturesTest(Temp):
    def test_save_list_serve_delete_and_prune(self):
        sid = "w-12345678"
        with mock.patch.object(captures, "limit", return_value=10):
            for _ in range(13):
                captures.save(sid, b"\xff\xd8jpeg")
        rows = captures.photos(sid)
        self.assertEqual(len(rows), 10)
        self.assertTrue(captures.photo_path(sid, rows[0]["name"]).is_file())
        captures.delete_photo(sid, rows[0]["name"])
        self.assertEqual(len(captures.photos(sid)), 9)

    def test_path_traversal_rejected(self):
        for name in ("../../etc/passwd", "photo_1.jpg", "photo_20240101_000000.jpg/../x"):
            with self.assertRaises(FileNotFoundError):
                captures.photo_path("w-12345678", name)
        with self.assertRaises(ValueError):
            captures.folder("../x")
        with self.assertRaises(ValueError):
            captures.clips_folder("../../x")

    def test_clips_and_purge(self):
        folder = captures.clips_folder("abcd1234")
        folder.mkdir(parents=True)
        (folder / "seg_20240101_000000.mp4").write_bytes(b"x" * 10)
        (folder / "other.txt").write_text("no")
        self.assertEqual([c["name"] for c in captures.clips("abcd1234")], ["seg_20240101_000000.mp4"])
        captures.save("c-abcd1234", b"j")
        self.assertEqual(captures.purge("c-abcd1234", "abcd1234"), {"photos": 1, "clips": 1})
        self.assertEqual(captures.usage("c-abcd1234", "abcd1234")["clips"], 0)

    def test_take_applies_options_transform(self):
        row = {"id": "c-abcdef12", "kind": "ip", "main": False, "device": "rtsp://10.0.0.1/x"}
        async def fake(source):
            return b"\xff\xd8raw"
        with mock.patch.object(live, "snapshot_bytes", fake), mock.patch.object(captures, "transform", lambda data, opts: data + b"!"):
            photo = asyncio.run(captures.take(row))
        self.assertEqual(captures.photo_path("c-abcdef12", photo["name"]).read_bytes(), b"\xff\xd8raw!")


class MotionTest(Temp):
    def frames(self, shift):
        a = np.zeros((36, 64), dtype=np.int16)
        b = a.copy()
        b[:, :shift] = 200
        return a, b

    def test_threshold_and_detection(self):
        a, b = self.frames(30)
        self.assertTrue(motion.moved(a, b, 5))
        a, b = self.frames(1)
        self.assertFalse(motion.moved(a, b, 3))
        self.assertTrue(motion.threshold(10) < motion.threshold(1))
        self.assertFalse(motion.moved(None, a, 10))

    def test_check_alerts_once_per_cooldown(self):
        self.webcams(device("Cam", "/dev/video4"), main="/dev/video0")
        row = {"id": "c-abcdef12", "name": "Giardino", "kind": "ip", "main": False, "device": "rtsp://10.0.0.1/x"}
        opts = options.validate({"motion": True, "sensitivity": 8})
        still, moving = self.frames(0)[0], self.frames(40)[1]
        sequence = iter([still, moving, still, moving])

        async def fake_snapshot(source):
            return b"jpg"

        with mock.patch.object(live, "snapshot_bytes", fake_snapshot), mock.patch.object(motion, "decode", lambda jpeg: next(sequence)), \
                mock.patch.object(motion.desk, "show"):
            motion.FRAMES.clear()
            motion.LAST_ALERT.clear()
            for _ in range(4):
                asyncio.run(motion.check(row, opts, 60))
        self.assertEqual(len(events.recent()), 1)
        self.assertIn("Giardino", events.recent()[0]["text"])


class UnifiedTest(Temp):
    def test_overview_merges_local_infrared_and_ip(self):
        self.webcams(device("HD Webcam", "/dev/video0", "/dev/video2"))
        cameras.items = {"abcd1234": {"id": "abcd1234", "name": "Ingresso", "kind": "rtsp", "url": "rtsp://10.0.0.9/s", "created": 1, "retention_min": 5}}
        data = unified.overview()
        kinds = sorted(s["kind"] for s in data["sources"])
        self.assertEqual(kinds, ["infrared", "ip", "local"])
        ip = next(s for s in data["sources"] if s["kind"] == "ip")
        self.assertEqual(ip["record"]["id"], "abcd1234")
        self.assertNotIn("rtsp", str(data))

    def test_main_webcam_cannot_record_but_second_one_links_registry(self):
        self.webcams(device("HD Webcam", "/dev/video0"), device("Second", "/dev/video4", bus="usb-2"), main="/dev/video0")
        main_id = live.local_id(device("HD Webcam", "/dev/video0"))
        second_id = live.local_id(device("Second", "/dev/video4", bus="usb-2"))
        with self.assertRaises(ValueError):
            unified.set_record(main_id, {"enabled": True})
        with mock.patch.object(cameras, "save"):
            view = unified.set_record(second_id, {"enabled": True, "consent": True, "record": True})
        self.assertTrue(view["recording"])
        self.assertEqual(len(cameras.items), 1)
        self.assertEqual(unified.registry_of(live.find(second_id))["url"], "/dev/video4")

    def test_remove_ip_source_cleans_everything(self):
        cameras.items = {"abcd1234": {"id": "abcd1234", "name": "Ingresso", "kind": "rtsp", "url": "rtsp://10.0.0.9/s", "created": 1, "retention_min": 5}}
        options.put("c-abcd1234", {"alias": "x"})
        captures.save("c-abcd1234", b"j")
        with mock.patch.object(cameras, "save"):
            removed = unified.remove("c-abcd1234")
        self.assertEqual(removed["photos"], 1)
        self.assertEqual(cameras.items, {})
        self.assertNotIn("c-abcd1234", options.read())


class ApiTest(Temp):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        assert cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS).status_code == 200
        cls.display = TestClient(atena_supervisor.public)

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(access, "is_local", lambda request: True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_overview_options_and_photo_routes(self):
        self.webcams(device("HD Webcam", "/dev/video0"))
        sid = live.local_id(device("HD Webcam", "/dev/video0"))
        self.assertEqual(self.admin.get("/api/cameras/overview", headers=HEADERS).json()["sources"][0]["id"], sid)
        put = self.admin.put(f"/api/cameras/source/{sid}/options", json={"room": "studio", "rotate": 180}, headers=HEADERS)
        self.assertEqual((put.status_code, put.json()["rotate"]), (200, 180))
        self.assertEqual(self.admin.put("/api/cameras/source/w-00000000/options", json={}, headers=HEADERS).status_code, 404)
        captures.save(sid, b"\xff\xd8jpg")
        name = self.admin.get(f"/api/cameras/source/{sid}/photos", headers=HEADERS).json()["photos"][0]["name"]
        self.assertEqual(self.admin.get(f"/api/cameras/source/{sid}/photos/{name}", headers=HEADERS).content, b"\xff\xd8jpg")
        self.assertEqual(self.admin.get(f"/api/cameras/source/{sid}/photos/..%2F..%2Fx", headers=HEADERS).status_code, 404)

    def test_discover_and_probe_need_safe_input(self):
        self.assertEqual(self.admin.post("/api/cameras/discover", json={}, headers=HEADERS).status_code, 400)
        self.assertEqual(self.admin.post("/api/cameras/discover", json={"confirm": True, "network": "8.8.8.0/24"}, headers=HEADERS).status_code, 400)
        self.assertFalse(self.admin.post("/api/cameras/probe", json={"url": "rtsp://8.8.8.8/x"}, headers=HEADERS).json()["ok"])

    def test_hidden_and_infrared_not_served_to_display(self):
        self.webcams(device("HD Webcam", "/dev/video0", "/dev/video2"))
        hidden = live.local_id(device("HD Webcam", "/dev/video0"))
        options.put(hidden, {"hidden": True})
        ir = live.ir_id(device("HD Webcam", "/dev/video0"))
        self.assertEqual(self.display.get(f"/api/cameras/live/{hidden}.jpg", headers=HEADERS).status_code, 404)
        self.assertEqual(self.display.get(f"/api/cameras/live/{ir}.jpg", headers=HEADERS).status_code, 404)

    def test_presets_build_endpoint(self):
        r = self.admin.post("/api/cameras/presets/build", json={"brand": "tapo", "host": "192.168.1.8", "user": "a", "password": "b"}, headers=HEADERS)
        self.assertEqual(r.json()["url"], "rtsp://a:b@192.168.1.8:554/stream1")
        self.assertEqual(self.admin.post("/api/cameras/presets/build", json={"brand": "zzz", "host": "1.1.1.1"}, headers=HEADERS).status_code, 400)


if __name__ == "__main__":
    unittest.main()
