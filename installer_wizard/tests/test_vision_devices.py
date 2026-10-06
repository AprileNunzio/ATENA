import asyncio
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.vision import devices as dev
from features.vision import ir_configure, ir_emitter, webcams

LIST = """HD Webcam: HD Webcam (usb-0000:00:14.0-3):
\t/dev/video0
\t/dev/video1
\t/dev/video2
\t/dev/video3
\t/dev/media0

Integrated Camera: Integrated C (usb-0000:00:14.0-8):
\t/dev/video4
\t/dev/video5
"""

RGB_INFO = """Driver Info:
\tDriver name      : uvcvideo
\tCard type        : HD Webcam: HD Webcam
\tBus info         : usb-0000:00:14.0-3
\tCapabilities     : 0x84a00001
\t\tVideo Capture
\t\tMetadata Capture
\t\tStreaming
\tDevice Caps      : 0x04200001
\t\tVideo Capture
\t\tStreaming
\t\tExtended Pix Format
"""

META_INFO = RGB_INFO.replace("Device Caps      : 0x04200001\n\t\tVideo Capture\n\t\tStreaming\n\t\tExtended Pix Format",
                             "Device Caps      : 0x04a00000\n\t\tMetadata Capture\n\t\tStreaming\n\t\tExtended Pix Format")

RGB_FORMATS = """ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\t\tInterval: Discrete 0.067s (15.000 fps)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t[1]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.100s (10.000 fps)
"""

IR_FORMATS = """ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'GREY' (8-bit Greyscale)
\t\tSize: Discrete 640x360
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 340x340
\t\t\tInterval: Discrete 0.033s (30.000 fps)
"""

BUILTIN_FORMATS = RGB_FORMATS.replace("1920x1080", "1280x720")


def inspector(path):
    table = {
        "/dev/video0": (RGB_INFO, RGB_FORMATS),
        "/dev/video1": (META_INFO, ""),
        "/dev/video2": (RGB_INFO.replace("HD Webcam: HD Webcam", "HD Webcam: IR Camera"), IR_FORMATS),
        "/dev/video3": (META_INFO, ""),
        "/dev/video4": (RGB_INFO.replace("HD Webcam: HD Webcam", "Integrated Camera"), BUILTIN_FORMATS),
        "/dev/video5": (META_INFO, ""),
    }
    info, formats = table[path]
    return dev.parse_info(info), dev.parse_formats(formats)


def usb_ids(path):
    return {"vendor": "0c45", "product": "6366", "maker": "Sonix", "model": "HD Webcam"} if path in ("/dev/video0",) else \
        {"vendor": "04f2", "product": "b6c1", "maker": "Chicony", "model": "Integrated Camera"}


class ParseTest(unittest.TestCase):
    def test_list_groups_nodes_by_physical_device(self):
        groups = dev.parse_list(LIST)
        self.assertEqual([g["name"] for g in groups], ["HD Webcam: HD Webcam", "Integrated Camera: Integrated C"])
        self.assertEqual(groups[0]["nodes"], ["/dev/video0", "/dev/video1", "/dev/video2", "/dev/video3"])
        self.assertEqual(groups[0]["bus"], "usb-0000:00:14.0-3")

    def test_formats_keep_sizes_and_best_fps(self):
        formats = dev.parse_formats(RGB_FORMATS)
        self.assertEqual(formats["MJPG"][(1920, 1080)], 30.0)
        self.assertEqual(formats["YUYV"][(1280, 720)], 10.0)
        self.assertEqual(set(dev.parse_formats(IR_FORMATS)), {"GREY"})

    def test_device_caps_decide_metadata_nodes_not_the_union(self):
        info = dev.parse_info(META_INFO)
        self.assertIn("Metadata Capture", info["caps"])
        self.assertNotIn("Video Capture", info["caps"])
        self.assertEqual(info["driver"], "uvcvideo")
        self.assertIn("Video Capture", dev.parse_info(RGB_INFO)["caps"])
        self.assertNotIn("Metadata Capture", dev.parse_info(RGB_INFO)["caps"])

    def test_classification(self):
        self.assertEqual(dev.classify(dev.parse_info(META_INFO), {}), "meta")
        self.assertEqual(dev.classify(dev.parse_info(RGB_INFO), dev.parse_formats(RGB_FORMATS)), "rgb")
        self.assertEqual(dev.classify(dev.parse_info(RGB_INFO), dev.parse_formats(IR_FORMATS)), "ir")
        mixed = dev.parse_formats(RGB_FORMATS.replace("MJPG", "GREY"))
        self.assertEqual(dev.classify(dev.parse_info(RGB_INFO), mixed, "Cam IR"), "ir")
        self.assertEqual(dev.classify(dev.parse_info(RGB_INFO), mixed, "Cam"), "rgb")

    def test_best_mode_prefers_the_format_order_then_the_biggest_size(self):
        formats = dev.parse_formats(RGB_FORMATS)
        self.assertEqual(dev.best_mode(formats, ("MJPG", "YUYV")), {"fourcc": "MJPG", "width": 1920, "height": 1080, "fps": 30.0})
        self.assertEqual(dev.best_mode(formats, ("YUYV",))["width"], 1280)
        self.assertEqual(dev.best_mode(formats, ("MJPG",), limit=(1280, 720))["width"], 640)
        self.assertIsNone(dev.best_mode(formats, ("H264",)))

    def test_ids_are_read_from_sysfs(self):
        root = Path(tempfile.mkdtemp())
        node = root / "video2" / "device"
        node.mkdir(parents=True)
        (root / "video2" / "idVendor").write_text("0c45\n")
        (root / "video2" / "idProduct").write_text("6366\n")
        ids = dev.read_usb_ids("/dev/video2", root)
        self.assertEqual((ids["vendor"], ids["product"]), ("0c45", "6366"))
        self.assertEqual(dev.read_usb_ids("/dev/video9", root), {})


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.devices = dev.build(dev.parse_list(LIST), inspector, usb_ids)

    def test_dual_sensor_camera_is_one_device_with_two_roles(self):
        main = next(d for d in self.devices if d["has_ir"])
        self.assertEqual((main["rgb"], main["ir"]), ("/dev/video0", "/dev/video2"))
        self.assertEqual(main["meta"], ["/dev/video1", "/dev/video3"])
        self.assertEqual(main["id"], "0c45:6366@usb-0000:00:14.0-3")
        self.assertEqual((main["rgb_mode"]["width"], main["rgb_mode"]["fourcc"]), (1920, "MJPG"))
        self.assertEqual((main["ir_mode"]["fourcc"], main["ir_mode"]["width"]), ("GREY", 640))

    def test_plain_webcam_has_no_ir(self):
        plain = next(d for d in self.devices if not d["has_ir"])
        self.assertEqual((plain["rgb"], plain["ir"]), ("/dev/video4", None))

    def test_choice_prefers_ir_and_respects_overrides(self):
        auto = dev.choose(self.devices)
        self.assertEqual((auto["rgb"], auto["ir"]), ("/dev/video0", "/dev/video2"))
        self.assertEqual(dev.choose(self.devices, ir_override="off")["ir"], None)
        self.assertEqual(dev.choose(self.devices, rgb_override="/dev/video4")["rgb"], "/dev/video4")
        self.assertEqual(dev.choose(self.devices, ir_override="not-a-path")["ir"], "/dev/video2")
        self.assertEqual(dev.choose([]), {"device": None, "rgb": None, "ir": None, "rgb_mode": None, "ir_mode": None})

    def test_signature_changes_with_hotplug(self):
        before = dev.signature(self.devices)
        self.assertNotEqual(before, dev.signature(self.devices[:1]))
        self.assertEqual(before, dev.signature(list(reversed(self.devices))))


class ScanTest(unittest.TestCase):
    def test_scan_selects_the_dual_sensor_camera_without_touching_drivers(self):
        driver = mock.Mock()
        with mock.patch.object(dev, "read_usb_ids", usb_ids):
            state = webcams.scan(inspector, lister=lambda: LIST, usb=lambda: [], driver=driver)
        self.assertEqual(state["selected"]["ir"], "/dev/video2")
        self.assertEqual(state["problems"], [])
        driver.assert_not_called()

    def test_camera_on_usb_without_nodes_triggers_the_driver_attempt(self):
        driver = mock.Mock(return_value="uvcvideo caricato senza riavviare")
        usb = lambda: [{"bus": "1-3:1.0", "vendor": "0c45", "product": "6366", "name": "CA20"}]
        state = webcams.scan(inspector, lister=lambda: "", usb=usb, driver=driver)
        driver.assert_called_once()
        self.assertIn("nessun", state["problems"][0].lower() + " nessun")
        self.assertEqual(state["devices"], [])

    def test_missing_v4l_utils_is_reported_not_raised(self):
        def lister():
            raise FileNotFoundError("v4l-utils non installato")
        state = webcams.scan(inspector, lister=lister, usb=lambda: [])
        self.assertEqual(state["problems"], ["v4l-utils non installato"])

    def test_describe(self):
        main = dev.build(dev.parse_list(LIST), inspector, usb_ids)[0]
        self.assertEqual(webcams.describe(main), "RGB 1920x1080 + infrarossi 640x360")

    @unittest.skipIf(os.name == "nt", "i nomi di sysfs contengono i due punti")
    def test_usb_video_interfaces_are_read_from_sysfs(self):
        root = Path(tempfile.mkdtemp())
        (root / "1-3:1.0").mkdir()
        (root / "1-3:1.0" / "bInterfaceClass").write_text("0e\n")
        (root / "1-3").mkdir()
        (root / "1-3" / "idVendor").write_text("0c45\n")
        (root / "1-3" / "idProduct").write_text("6366\n")
        (root / "1-3" / "product").write_text("CA20 IR\n")
        (root / "2-1:1.0").mkdir()
        (root / "2-1:1.0" / "bInterfaceClass").write_text("03\n")
        found = webcams.usb_video_interfaces(root)
        self.assertEqual([(f["vendor"], f["product"], f["name"]) for f in found], [("0c45", "6366", "CA20 IR")])
        self.assertEqual(webcams.usb_video_interfaces(root / "missing"), [])

    def test_refresh_publishes_events_only_on_change(self):
        manager = webcams.Webcams.__new__(webcams.Webcams)
        manager.state, manager.sig = {}, ""
        published = []
        manager.publish = lambda new: (published.append(new), setattr(manager, "state", new), setattr(manager, "sig", dev.signature(new["devices"])))
        with mock.patch.object(dev, "read_usb_ids", usb_ids), \
                mock.patch.object(webcams, "inspect", inspector), \
                mock.patch.object(webcams, "run_v4l", lambda args, timeout=8.0: LIST), \
                mock.patch.object(webcams, "usb_video_interfaces", lambda root=None: []):
            asyncio.run(manager.refresh())
            asyncio.run(manager.refresh())
        self.assertEqual(len(published), 1)


def tarball(files: dict, extra=None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(data))
        if extra:
            extra(tar)
    return buf.getvalue()


class EmitterToolTest(unittest.TestCase):
    def test_verified_archive_is_extracted_under_the_root(self):
        data = tarball({"usr/local/bin/linux-enable-ir-emitter": b"#!/bin/sh\n", "etc/x.conf": b"a"})
        root = Path(tempfile.mkdtemp())
        import hashlib
        count = ir_emitter.verify_and_extract(data, root, hashlib.sha256(data).hexdigest())
        self.assertEqual(count, 2)
        self.assertTrue((root / "usr/local/bin/linux-enable-ir-emitter").exists())

    def test_wrong_checksum_extracts_nothing(self):
        data = tarball({"usr/bin/x": b"a"})
        root = Path(tempfile.mkdtemp())
        with self.assertRaises(ValueError):
            ir_emitter.verify_and_extract(data, root)
        self.assertEqual(list(root.iterdir()), [])

    def test_unsafe_members_are_rejected(self):
        import hashlib
        for bad in ("../evil", "/etc/passwd", "home/user/.bashrc"):
            data = tarball({bad: b"x"})
            with self.assertRaises(ValueError, msg=bad):
                ir_emitter.verify_and_extract(data, Path(tempfile.mkdtemp()), hashlib.sha256(data).hexdigest())

        def device(tar):
            info = tarfile.TarInfo("usr/dev")
            info.type = tarfile.CHRTYPE
            tar.addfile(info)
        data = tarball({"usr/ok": b"1"}, device)
        with self.assertRaises(ValueError):
            ir_emitter.verify_and_extract(data, Path(tempfile.mkdtemp()), hashlib.sha256(data).hexdigest())

    def test_command_hint_and_status_without_the_tool(self):
        hint = ir_emitter.command_hint("/dev/video2", {"width": 640, "height": 360})
        self.assertIn("--device /dev/video2 --width 640 --height 360", hint)
        self.assertTrue(hint.endswith("configure --no-gui"))
        self.assertEqual(ir_configure.arguments("/x", "/dev/video2", None)[-2:], ["configure", "--no-gui"])
        with mock.patch.object(ir_emitter, "tool_path", return_value=None), mock.patch.object(ir_emitter, "service_active", return_value=False):
            status = ir_emitter.status("/dev/video2", None)
        self.assertFalse(status["tool"])
        self.assertEqual(status["version"], ir_emitter.VERSION)

    def test_enable_requires_tool_and_configuration(self):
        with mock.patch.object(ir_emitter, "tool_path", return_value=None):
            with self.assertRaises(RuntimeError):
                asyncio.run(ir_emitter.enable_service())
        with mock.patch.object(ir_emitter, "tool_path", return_value="/x"), mock.patch.object(ir_emitter, "configured", return_value=False):
            with self.assertRaises(RuntimeError):
                asyncio.run(ir_emitter.enable_service())

    def test_configured_looks_for_files_in_the_config_dirs(self):
        empty, full = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        (full / "video2.json").write_text("{}")
        self.assertFalse(ir_emitter.configured((empty, Path("/nonexistent"))))
        self.assertTrue(ir_emitter.configured((empty, full)))


if __name__ == "__main__":
    unittest.main()


class PersonPhotoTest(unittest.TestCase):
    def test_photo_is_served_from_disk_when_vision_is_down(self):
        from features.vision import api
        root = Path(tempfile.mkdtemp())
        (root / "ospite-1").mkdir()
        (root / "ospite-1" / "photo.jpg").write_bytes(b"\xff\xd8jpeg")
        with mock.patch.object(api, "FACES", root):
            res = asyncio.run(api.admin_person_photo("Ospite-1", "admin"))
            self.assertEqual(res.body, b"\xff\xd8jpeg")
            seen = []

            async def proxy(path):
                seen.append(path)
                return "proxied"
            with mock.patch.object(api, "vision_proxy", proxy):
                self.assertEqual(asyncio.run(api.admin_person_photo("../../etc", "admin")), "proxied")
            self.assertEqual(seen, ["/people/etc/photo.jpg"])
