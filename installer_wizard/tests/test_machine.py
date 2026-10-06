import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import machine
import packages
import setup_api
from steps import STEP_BY_ID, STEPS_DIR

STEPS = Path(__file__).resolve().parents[2] / "scripts" / "os" / "steps"
GB = 2 ** 30


class ClassTest(unittest.TestCase):
    def detect(self, ram_gb, model="", gpu=False):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(model + "\x00")
        self.addCleanup(Path(f.name).unlink)
        tree = Path(f.name) if model else Path("/nonexistent/model")
        with mock.patch.object(machine, "MODEL_TREE", tree), \
                mock.patch.object(machine.psutil, "virtual_memory", return_value=mock.Mock(total=ram_gb * GB)):
            return machine.detect(gpu)

    def test_classes(self):
        self.assertEqual(self.detect(8, "Raspberry Pi 5 Model B Rev 1.0"), "pi")
        self.assertEqual(self.detect(4), "small")
        self.assertEqual(self.detect(16), "standard")
        self.assertEqual(self.detect(16, gpu=True), "powerful")
        self.assertEqual(self.detect(32), "powerful")

    def test_saved_class_wins(self):
        with mock.patch.object(machine, "DEMO", False):
            self.assertEqual(machine.current({"ATENA_MACHINE": "pi"}), "pi")
            self.assertTrue(machine.heavy("brain_local", {"ATENA_MACHINE": "pi"}))
            self.assertFalse(machine.heavy("brain_local", {"ATENA_MACHINE": "standard"}))

    def test_small_machines_start_light_with_the_brain_in_the_cloud(self):
        for cls, brain, voice in (("pi", "cloud", False), ("small", "cloud", False), ("standard", "local", True)):
            with self.subTest(cls=cls), mock.patch.object(machine, "current", return_value=cls), \
                    mock.patch.object(setup_api, "DEMO", False), mock.patch("glob.glob", return_value=[]):
                self.assertEqual(machine.BRAIN[cls], brain)
                self.assertEqual("voice" in setup_api.suggested_packages(), voice)

    def test_catalog_marks_heavy_packages(self):
        with mock.patch.object(machine, "current", return_value="pi"):
            heavy = {p["id"] for p in packages.catalog() if p["heavy"]}
        self.assertIn("brain_local", heavy)
        self.assertNotIn("voice", heavy)


class ScriptTest(unittest.TestCase):
    def run_preflight(self, expr):
        script = f'source <(sed "/^step_main/d" {STEPS / "10-preflight.sh"}); {expr}'
        env = {"PATH": "/usr/bin:/bin", "ATENA_ETC": "/nonexistent"}
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, timeout=20).stdout.strip()

    def test_a_raspberry_pi_gets_small_models(self):
        self.assertEqual(self.run_preflight("select_llm 8 0 pi; select_fast_llm 8 0 pi; select_llm 4 0 pi").split(),
                         ["qwen2.5:1.5b", "qwen2.5:0.5b", "qwen2.5:0.5b"])
        self.assertEqual(self.run_preflight("select_llm 32 0 powerful"), "qwen2.5:7b")

    def test_memory_step_is_registered(self):
        step = STEP_BY_ID["memory"]
        self.assertFalse(step.critical)
        self.assertTrue((STEPS_DIR / step.script).name == "15-memory.sh")
        self.assertTrue((STEPS / step.script).exists())
        self.assertEqual(subprocess.run(["bash", "-n", str(STEPS / step.script)]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
