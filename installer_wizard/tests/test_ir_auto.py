import asyncio
import unittest
from unittest import mock

from features.vision import ir_auto, ir_configure


class PromptTests(unittest.TestCase):

    def test_detects_question_at_end(self):
        self.assertTrue(ir_auto.is_prompt("[INFO] trying\nDid you see the emitter flashing? Yes/No"))
        self.assertTrue(ir_auto.is_prompt("Continue? (y/n)"))

    def test_ignores_progress_and_answers(self):
        self.assertFalse(ir_auto.is_prompt("[INFO] Stand in front of the camera"))
        self.assertFalse(ir_auto.is_prompt("Did you see it? Yes/No\n> N"))
        self.assertFalse(ir_auto.is_prompt(""))

    def test_skipper_says_no_then_yes_once_per_prompt(self):
        respond = ir_auto.skipper(2)
        out = "a?"
        self.assertEqual(respond(out), "n")
        self.assertIsNone(respond(out))
        self.assertEqual(respond(out + "\n> N\nb?"), "n")
        self.assertEqual(respond(out + "\n> N\nb?\n> N\nc?"), "y")

    def test_candidates_put_selected_first_and_dedupe(self):
        snap = {"selected": {"ir": "/dev/video4"},
                "devices": [{"ir": "/dev/video2", "ir_mode": {"width": 1}}, {"ir": "/dev/video4", "ir_mode": {"width": 2}},
                            {"ir": "/dev/video4", "ir_mode": {"width": 2}}, {"ir": None}]}
        self.assertEqual([c["device"] for c in ir_auto.candidates(snap)], ["/dev/video4", "/dev/video2"])


class FlowTests(unittest.TestCase):

    def setUp(self):
        ir_auto.state.update(running=False, stop=False, stage="", device="", attempt=0, result="", log=[])

    def run_flow(self, outcomes, options):
        calls = []

        async def fake_attempt(tool, item, skips):
            calls.append((item["device"], skips))
            return outcomes.pop(0)

        enabled = []

        async def fake_enable():
            enabled.append(True)

        async def fake_refresh(force=False):
            return {}

        with mock.patch.object(ir_auto, "attempt", fake_attempt), \
                mock.patch.object(ir_auto.ir_emitter, "tool_path", return_value="/x"), \
                mock.patch.object(ir_auto.ir_emitter, "enable_service", fake_enable), \
                mock.patch.object(ir_auto.cams.webcams, "refresh", fake_refresh), \
                mock.patch.object(ir_auto, "candidates", return_value=options):
            result = asyncio.run(ir_auto.execute())
        return result, calls, enabled

    def test_success_enables_service(self):
        result, calls, enabled = self.run_flow(["dark", "ok"], [{"device": "/dev/video2", "mode": None}])
        self.assertEqual(calls, [("/dev/video2", 0), ("/dev/video2", 1)])
        self.assertTrue(enabled)
        self.assertIn("attivato", result)

    def test_blind_node_moves_to_next_candidate(self):
        result, calls, enabled = self.run_flow(["blind", "ok"], [{"device": "/dev/video2", "mode": None}, {"device": "/dev/video3", "mode": None}])
        self.assertEqual(calls, [("/dev/video2", 0), ("/dev/video3", 0)])
        self.assertIn("/dev/video3", result)

    def test_nothing_works_does_not_enable(self):
        result, calls, enabled = self.run_flow(["dark"] * 5, [{"device": "/dev/video2", "mode": None}])
        self.assertEqual(len(calls), ir_auto.MAX_SKIPS + 1)
        self.assertFalse(enabled)

    def test_no_candidates(self):
        result, calls, enabled = self.run_flow([], [])
        self.assertIn("nessun sensore", result)

    def test_stop_flag_interrupts(self):
        ir_auto.state["stop"] = True
        result, calls, _ = self.run_flow([], [{"device": "/dev/video2", "mode": None}])
        self.assertEqual(calls, [])
        self.assertIn("interrotta", result)

    def test_start_refuses_when_busy(self):
        ir_auto.state["running"] = True
        with self.assertRaises(RuntimeError):
            ir_auto.start()


class ResponderTests(unittest.TestCase):

    def test_pump_answers_through_responder(self):
        sent = []

        class Proc:
            returncode = None

        chunks = [b"Did you see it? Yes/No", b""]

        def fake_read(fd):
            return chunks.pop(0)

        async def fake_finish(proc):
            return None

        ir_configure.session.update(running=True, output="")
        ir_configure.handle.update(fd=1, responder=lambda out: "y" if out.endswith("No") else None)
        with mock.patch.object(ir_configure, "wait_read", fake_read), mock.patch.object(ir_configure, "finish", fake_finish), \
                mock.patch.object(ir_configure.os, "write", lambda fd, data: sent.append(data)):
            asyncio.run(ir_configure.pump(1, Proc()))
        self.assertEqual(sent, [b"y\n"])
        ir_configure.handle.update(fd=None, responder=None)
        ir_configure.session["running"] = False


if __name__ == "__main__":
    unittest.main()
