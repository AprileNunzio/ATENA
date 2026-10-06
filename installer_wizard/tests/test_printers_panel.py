import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.printers import service
from features.whiteboard.printer import PrinterManager

ROOT = Path(__file__).resolve().parents[1]


class ValidationTest(unittest.TestCase):
    def test_valid_printers(self):
        ok = service.validate({"name": "Ufficio", "type": "laser_2d", "connection": "network", "address": "192.168.1.10", "port": 9100})
        self.assertEqual(ok["address"], "192.168.1.10")
        self.assertEqual(service.validate({"name": "Ender", "type": "3d", "connection": "network", "address": "http://10.0.0.5:7125"})["port"], 7125)
        self.assertEqual(service.validate({"name": "Laser", "type": "engraver", "connection": "usb", "address": "/dev/ttyUSB0"})["address"], "/dev/ttyUSB0")

    def test_rejections(self):
        base = {"name": "X", "type": "laser_2d", "connection": "network", "address": "printer.local", "port": 9100}
        for change in ({"name": "<script>"}, {"name": ""}, {"type": "virtual_pdf"}, {"connection": "system"}, {"port": 70000},
                       {"address": "a; rm -rf /"}, {"connection": "usb", "address": "/etc/passwd"}, {"address": "file:///etc/passwd"}):
            with self.subTest(change=change), self.assertRaises(service.PrinterError):
                service.validate({**base, **change})

    def test_options_are_clamped(self):
        o = service.clean_options({"paper": "A0", "copies": 500, "laser_power": -5, "color": 0})
        self.assertEqual((o["paper"], o["copies"], o["laser_power"], o["color"]), ("A4", 99, 0, False))

    def test_lp_arguments(self):
        args = PrinterManager.lp_options({"copies": 2, "paper": "A3", "duplex": True, "orientation": "landscape", "color": False, "quality": "high"})
        self.assertEqual(args[:2], ["-n", "2"])
        for flag in ("media=A3", "sides=two-sided-long-edge", "orientation-requested=4", "print-color-mode=monochrome", "print-quality=5"):
            self.assertIn(flag, args)


class ListingTest(unittest.TestCase):
    def test_api_keys_never_leave_and_options_persist_privately(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(service, "OPTIONS_FILE", Path(root) / "o.json"):
            fake = mock.Mock()
            fake.custom_printers = [{"id": "p1"}]
            fake.list_printers.return_value = [{"id": "p1", "name": "Ufficio", "type": "laser_2d", "connection": "network", "api_key": "SECRET"}]
            with mock.patch.object(service, "printer_manager", fake):
                printers = service.Printers()
                printers.set_options("p1", {"copies": 3, "atena_default": True})
                row = printers.listing()[0]
                self.assertNotIn("api_key", row)
                self.assertTrue(row["has_api_key"] and row["atena_default"])
                self.assertEqual(row["options"]["copies"], 3)
                self.assertEqual((Path(root) / "o.json").stat().st_mode & 0o777, 0o600)
                self.assertEqual(service.Printers().default_id, "p1")
                with self.assertRaises(KeyError):
                    printers.set_options("nope", {})
                fake.list_printers.return_value.append({"id": "cups_x", "name": "x", "type": "laser_2d", "connection": "system"})
                with self.assertRaises(service.PrinterError):
                    printers.remove("cups_x")

    def test_install_validates_before_calling_cups(self):
        printers = service.Printers()
        with mock.patch.object(service.Printers, "can_install", return_value=True), mock.patch.object(service.subprocess, "run") as run:
            for body in ({"uri": "ipp://h/ipp/print; reboot", "queue": "q"}, {"uri": "socket://h:9100", "queue": "q"},
                         {"uri": "ipp://h/ipp/print", "queue": "-rf"}):
                with self.assertRaises(service.PrinterError):
                    printers.install(body)
            run.assert_not_called()


class I18nCoverageTest(unittest.TestCase):
    KEY = re.compile(r'(?:A\.t\(\s*"|data-i18n(?:-placeholder)?="admin:|HTTPException\(\d+, "|Error\(")((?:printers|nvr|bus|twin|scene|feedback)\.[a-z0-9_.]+)"')

    def test_every_key_used_by_the_panels_exists_in_every_language(self):
        files = [*ROOT.glob("features/printers/*.*"), *ROOT.glob("features/nvr/*.*"), *ROOT.glob("features/twin/*.*"),
                 *ROOT.glob("features/scene/*.*"), ROOT / "features" / "habits" / "admin.js", ROOT / "features" / "habits" / "admin.html",
                 ROOT / "backend" / "bus_api.py"]
        used = {k for f in files if f.suffix in (".js", ".html", ".py") for k in self.KEY.findall(f.read_text(encoding="utf-8"))}
        self.assertGreater(len(used), 40)
        for lang in ("it", "en"):
            data = json.loads((ROOT / "web" / "admin" / "language" / f"{lang}.json").read_text(encoding="utf-8"))
            for key in sorted(used):
                node = data
                for part in key.split("."):
                    node = node.get(part) if isinstance(node, dict) else None
                with self.subTest(lang=lang, key=key):
                    self.assertIsInstance(node, str)


if __name__ == "__main__":
    unittest.main()
