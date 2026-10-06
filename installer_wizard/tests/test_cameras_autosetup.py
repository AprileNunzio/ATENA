import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.cameras import autosetup
from features.vision import ir_auto

NOW = 1_000_000.0


class DueTest(unittest.TestCase):
    def due(self, **over):
        args = dict(device="/dev/video2", state="dark", configured=False, supported=True, busy=False, tried={}, dark_for=90, now=NOW)
        args.update(over)
        return autosetup.due(**args)

    def test_runs_when_dark_long_enough_and_never_tried(self):
        self.assertTrue(self.due())

    def test_waits_for_stable_darkness(self):
        self.assertFalse(self.due(dark_for=10))

    def test_skips_when_not_applicable(self):
        for over in ({"device": None}, {"state": "ok"}, {"configured": True}, {"supported": False}, {"busy": True}):
            self.assertFalse(self.due(**over), over)

    def test_retries_only_after_a_week(self):
        self.assertFalse(self.due(tried={"/dev/video2": NOW - 3600}))
        self.assertTrue(self.due(tried={"/dev/video2": NOW - 8 * 86400}))


class StepTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="irauto-"))
        patcher = mock.patch.object(autosetup, "FILE", self.dir / "ir_auto.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        ir_auto.state["running"] = False

    def run_step(self, dark_since, env="1"):
        started = []
        with mock.patch.object(autosetup.cams, "read_json", return_value={"state": "dark"}), \
                mock.patch.object(autosetup.cams.webcams, "state", {"selected": {"ir": "/dev/video2"}}), \
                mock.patch.object(autosetup.ir_emitter, "configured", return_value=False), \
                mock.patch.object(autosetup.ir_emitter, "tool_path", return_value=None), \
                mock.patch.object(autosetup, "supported", return_value=True), \
                mock.patch.object(autosetup, "env_get", return_value=env), \
                mock.patch.object(autosetup.ir_auto, "start", lambda: started.append(True)):
            result = asyncio.run(autosetup.step(dark_since))
        return result, started

    def test_starts_once_then_remembers(self):
        first, started = self.run_step(autosetup.time.time() - 120)
        self.assertEqual(started, [True])
        self.assertIn("/dev/video2", autosetup.read())
        _, again = self.run_step(first)
        self.assertEqual(again, [])

    def test_does_not_start_on_first_dark_reading(self):
        _, started = self.run_step(None)
        self.assertEqual(started, [])

    def test_switch_off_disables_it(self):
        _, started = self.run_step(autosetup.time.time() - 500, env="0")
        self.assertEqual(started, [])

    def test_reactivates_service_when_configured_but_inactive(self):
        enabled = []

        async def fake_enable():
            enabled.append(True)

        with mock.patch.object(autosetup.ir_emitter, "tool_path", return_value="/x"), mock.patch.object(autosetup.ir_emitter, "configured", return_value=True), \
                mock.patch.object(autosetup.ir_emitter, "service_active", return_value=False), mock.patch.object(autosetup.ir_emitter, "enable_service", fake_enable):
            asyncio.run(autosetup.keep_service())
        self.assertEqual(enabled, [True])


class ScriptsTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2] / "scripts" / "os" / "steps"

    def test_system_step_installs_camera_tools(self):
        text = (self.ROOT / "20-system.sh").read_text(encoding="utf-8")
        self.assertIn("ffmpeg", text)
        self.assertIn("v4l-utils", text)

    def test_vision_check_requires_v4l_tools(self):
        text = (self.ROOT / "57-vision.sh").read_text(encoding="utf-8")
        self.assertIn("command -v v4l2-ctl >/dev/null 2>&1 || return 1", text)


if __name__ == "__main__":
    unittest.main()
