import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
from features.nodes import adapt
from features.nodes import registry as registry_module

HEADERS = {"X-Atena-Request": "1"}

OLD = {"cores": 4, "ram_gb": 8, "avx2": True, "cameras": ["HD Webcam"], "audio_in": ["HD Webcam"], "ir_camera": False}
NEW = {"cores": 4, "ram_gb": 8, "avx2": True, "cameras": ["HD Webcam", "CA20 IR (infrarossi)"], "audio_in": ["HD Webcam"],
       "ir_camera": True, "gpu": "", "usb": []}


class PureTest(unittest.TestCase):
    def test_hardware_from_nodes_is_whitelisted_clamped_and_cleaned(self):
        dirty = {"cores": 99999, "ram_gb": "7.5", "avx2": 1, "cameras": ["Cam <script>"] + ["x"] * 30, "evil": "x" * 10,
                 "gpu": "NVIDIA" * 50, "ir_camera": True, "audio_in": "non una lista"}
        clean = adapt.clean_hardware(dirty)
        self.assertEqual(clean["cores"], 512)
        self.assertEqual(clean["ram_gb"], 7.5)
        self.assertNotIn("evil", clean)
        self.assertEqual(len(clean["cameras"]), 12)
        self.assertNotIn("<", clean["cameras"][0])
        self.assertEqual(len(clean["gpu"]), 60)
        self.assertEqual(clean["audio_in"], [])
        self.assertIsNone(adapt.clean_hardware("x"))
        self.assertEqual(adapt.clean_hardware({"cores": "boh"})["cores"], 0)

    def test_changes_are_described_in_italian(self):
        changes = adapt.diff(adapt.clean_hardware(OLD), adapt.clean_hardware(NEW))
        self.assertIn("Webcam collegato: CA20 IR (infrarossi)", changes)
        self.assertIn("Sensore infrarosso collegato", changes)
        removed = adapt.diff(adapt.clean_hardware(NEW), adapt.clean_hardware(OLD))
        self.assertIn("Sensore infrarosso scollegato", removed)
        self.assertIn("Webcam scollegato: CA20 IR (infrarossi)", removed)
        bigger = adapt.diff(adapt.clean_hardware(OLD), adapt.clean_hardware({**OLD, "ram_gb": 16, "cores": 8}))
        self.assertTrue(any("Memoria" in c for c in bigger) and any("Processore" in c for c in bigger))
        self.assertEqual(adapt.diff(None, adapt.clean_hardware(OLD)), [])
        self.assertEqual(adapt.diff(adapt.clean_hardware(OLD), adapt.clean_hardware(OLD)), [])

    def test_advice_depends_on_the_class_and_the_peripherals(self):
        old_pc = adapt.advice(adapt.clean_hardware({"cores": 2, "ram_gb": 3, "avx2": False, "cameras": ["x"]}))
        self.assertTrue(any("datato" in t for t in old_pc))
        self.assertTrue(any("solo i colori" in t for t in old_pc))
        self.assertTrue(any("Nessun microfono" in t for t in old_pc))
        strong = adapt.advice(adapt.clean_hardware({"cores": 16, "ram_gb": 32, "avx2": True, "ir_camera": True, "audio_in": ["m"]}))
        self.assertTrue(any("abbondante" in t for t in strong))
        self.assertTrue(any("anti-foto" in t for t in strong))
        self.assertTrue(any("Poca memoria" in t for t in adapt.advice(adapt.clean_hardware({"cores": 4, "ram_gb": 1, "avx2": True}))))

    def test_report_keeps_a_bounded_history_without_the_full_hardware(self):
        hardware = adapt.clean_hardware(NEW)
        history = []
        for _ in range(30):
            history = adapt.remember(history, adapt.build_report(hardware, adapt.clean_hardware(OLD)))
        self.assertEqual(len(history), adapt.HISTORY)
        self.assertNotIn("hardware", history[0])
        self.assertEqual(history[0]["class"], "mid")

    def test_master_hardware_summarises_cameras_and_infrared(self):
        webcams = {"devices": [{"name": "CA20", "has_ir": True}, {"name": "Interna", "has_ir": False}],
                   "usb_video": [{"name": "", "vendor": "0c45", "product": "6366"}]}
        hw = adapt.master_hardware({"cores": 8, "ram_gb": 16, "gpu": ""}, webcams, {"avx2": False}, ["Mic"])
        self.assertTrue(hw["ir_camera"])
        self.assertEqual(hw["cameras"], ["CA20 (infrarossi)", "Interna"])
        self.assertEqual(hw["usb"], ["0c45:6366"])
        self.assertEqual(hw["audio_in"], ["Mic"])


class RegistryTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(registry_module, "NODES_FILE", Path(tempfile.mkdtemp()) / "nodes.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.reg = registry_module.Registry()
        code = self.reg.new_code()["code"]
        self.token = self.reg.pair(code, "cucina-pi", {"name": "Cucina", "type": "satellite"})
        self.node = self.reg.authenticate("cucina-pi", self.token)

    def beat(self, hardware, adapted=False):
        return self.reg.heartbeat(self.node, {"version": "2.2.0", "hardware": hardware, "adapted": adapted}, "10.0.0.5")

    def test_command_exists_and_reaches_the_node_once(self):
        self.assertIn("adapt", registry_module.COMMANDS)
        self.reg.command("cucina-pi", "adapt")
        self.assertEqual(self.beat(OLD), ["adapt"])
        self.assertEqual(self.beat(OLD), [])

    def test_first_report_is_stored_then_only_changes_or_forced_scans_update_the_adaptation(self):
        self.beat(OLD)
        first = self.node["adaptation"]["at"]
        self.assertEqual(self.node["adaptation"]["changes"], [])
        self.beat(OLD)
        self.assertEqual(self.node["adaptation"]["at"], first)
        self.beat(NEW)
        self.assertIn("Sensore infrarosso collegato", self.node["adaptation"]["changes"])
        self.assertEqual(len(self.node["adaptations"]), 2)
        self.beat(NEW, adapted=True)
        self.assertTrue(self.node["adaptation"]["forced"])
        self.assertEqual(self.node["adaptation"]["changes"], [])

    def test_garbage_hardware_never_breaks_the_heartbeat(self):
        for bad in (None, "x", [], {"cores": "x"}):
            self.beat(bad)
        self.assertEqual(self.reg.listing()[0]["id"], "cucina-pi")
        self.assertNotIn("token", self.reg.listing()[0])


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = TestClient(atena_supervisor.admin)
        assert cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS).status_code == 200

    def test_master_adapt_returns_a_report_and_remembers_it(self):
        snap = Path(tempfile.mkdtemp()) / "hardware_master.json"
        with mock.patch.object(adapt, "SNAPSHOT", snap):
            first = self.admin.post("/api/nodes/master/adapt", headers=HEADERS)
            self.assertEqual(first.status_code, 200, first.text)
            body = first.json()
            for key in ("hardware", "changes", "advice", "class", "features", "at"):
                self.assertIn(key, body)
            self.assertTrue(body["forced"])
            self.assertEqual(self.admin.get("/api/nodes/master/adaptation", headers=HEADERS).json()["at"], body["at"])
            second = self.admin.post("/api/nodes/master/adapt", headers=HEADERS).json()
            self.assertEqual(second["changes"], [])

    def test_adapt_requires_login_and_nodes_overview_lists_the_command(self):
        anon = TestClient(atena_supervisor.admin)
        self.assertEqual(anon.post("/api/nodes/master/adapt", headers=HEADERS).status_code, 401)
        self.assertIn("adapt", self.admin.get("/api/nodes", headers=HEADERS).json()["commands"])

    def test_command_endpoint_accepts_adapt_for_a_node(self):
        with mock.patch.object(registry_module, "NODES_FILE", Path(tempfile.mkdtemp()) / "n.json"):
            reg = registry_module.Registry()
            with mock.patch("features.nodes.api.registry", reg):
                reg.pair(reg.new_code()["code"], "sala-pi", {"name": "Sala", "type": "display"})
                r = self.admin.post("/api/nodes/sala-pi/command/adapt", headers=HEADERS)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(reg.data["nodes"]["sala-pi"]["commands"], ["adapt"])


class AlsaTest(unittest.TestCase):
    def test_devices_are_parsed_and_missing_tools_are_harmless(self):
        output = "card 0: PCH [HDA Intel PCH], device 0: ALC Analog [ALC Analog]\ncard 1: Camera [HD Webcam], device 0: USB Audio [USB Audio]\n"
        fake = mock.Mock(stdout=output)
        with mock.patch.object(adapt.shutil, "which", return_value="/usr/bin/arecord"), mock.patch.object(adapt.subprocess, "run", return_value=fake):
            self.assertEqual(adapt.alsa_devices("arecord"), ["HDA Intel PCH", "HD Webcam"])
        with mock.patch.object(adapt.shutil, "which", return_value=None):
            self.assertEqual(adapt.alsa_devices("arecord"), [])
        self.assertIsNotNone(asyncio)


if __name__ == "__main__":
    unittest.main()
