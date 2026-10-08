import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

EAR = Path(__file__).resolve().parents[1] / "features" / "ear"
if str(EAR) not in sys.path:
    sys.path.append(str(EAR))

import recorder
import review_metrics as metrics
import tuning as tuning_module
from autolevel import AutoLevel

HAS_WAKE = lambda text: "atena" in text.lower()


class MetricsTest(unittest.TestCase):
    def test_agreement_is_word_based_and_ignores_accents(self):
        self.assertEqual(metrics.agreement("Accendi la luce", "accendi la luce"), 1.0)
        self.assertEqual(metrics.agreement("", ""), 1.0)
        self.assertEqual(metrics.agreement("ciao", ""), 0.0)
        self.assertEqual(metrics.agreement("perché sì", "perche si"), 1.0)
        self.assertLess(metrics.agreement("accendi la luce", "spegni il televisore"), 0.3)

    def test_missed_wake_when_review_hears_atena_but_nothing_handled(self):
        segments = [{"start": 10, "end": 12, "text": "Atena che ore sono"}]
        audit = metrics.wake_audit([{"kind": "heard", "t": 11.0, "text": "giarbis"}], segments, HAS_WAKE)
        self.assertEqual(audit["missed"], 1)

    def test_handled_wake_is_true_and_noise_trigger_is_false_instant(self):
        segments = [{"start": 1, "end": 3, "text": "Atena accendi la luce"}]
        events = [{"kind": "wake", "t": 2.0, "source": "instant"}, {"kind": "wake", "t": 40.0, "source": "instant"}]
        audit = metrics.wake_audit(events, segments, HAS_WAKE)
        self.assertEqual((audit["missed"], audit["true_wakes"], audit["false_instant"]), (0, 1, 1))

    def test_transcript_comparison_uses_the_utterance_window(self):
        segments = [{"start": 1, "end": 3, "text": "accendi la luce"}, {"start": 30, "end": 32, "text": "altro discorso"}]
        rows = metrics.compare_transcripts([{"kind": "transcript", "t": 3.5, "dur": 2.5, "text": "accendi la luce"}], segments)
        self.assertEqual(rows[0]["score"], 1.0)

    def test_level_report_flags_weak_and_clipped_voice(self):
        weak = metrics.level_report({"speech_p50": 0.008, "noise": 0.004, "clip_frac": 0.0})
        self.assertTrue(weak["weak"])
        self.assertGreater(weak["recommended_gain"], 5)
        loud = metrics.level_report({"speech_p50": 0.2, "noise": 0.003, "clip_frac": 0.1})
        self.assertTrue(loud["clipped"])
        self.assertFalse(loud["weak"])

    def test_summary_gives_advice_in_italian(self):
        reviews = [{"agreement": 0.4, "missed": 2, "true_wakes": 0, "false_instant": 0, "checked": 3, "weak": True,
                    "clipped": False, "snr_db": 5.0}] * 3
        summary = metrics.summarize(reviews)
        self.assertEqual(summary["chunks"], 3)
        self.assertGreaterEqual(len(summary["advice"]), 3)
        self.assertEqual(metrics.summarize([]), {"chunks": 0})


class TuningTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        tuning_module.TUNING_FILE = Path(self.dir) / "tuning.json"
        self.tuning = tuning_module.Tuning()
        os.environ.pop("ATENA_EAR_AUTOTUNE", None)

    def review(self, **kw):
        base = {"missed": 0, "false_instant": 0, "true_wakes": 0, "weak": False, "clipped": False}
        return {**base, **kw}

    def test_missed_wakes_lower_the_threshold_gradually(self):
        applied = []
        for _ in range(tuning_module.WINDOW_CHUNKS):
            applied += self.tuning.observe(self.review(missed=1))
        self.assertEqual(self.tuning.wake_threshold(), 0.45)
        self.assertEqual(applied[0]["key"], "wake_threshold")

    def test_false_wakes_raise_the_threshold(self):
        for _ in range(tuning_module.WINDOW_CHUNKS):
            self.tuning.observe(self.review(false_instant=1))
        self.assertEqual(self.tuning.wake_threshold(), 0.55)

    def test_threshold_never_leaves_its_bounds(self):
        for _ in range(tuning_module.WINDOW_CHUNKS * 20):
            self.tuning.observe(self.review(missed=1))
        self.assertGreaterEqual(self.tuning.wake_threshold(), tuning_module.THRESHOLD_MIN)

    def test_weak_voice_raises_gain_limits(self):
        for _ in range(tuning_module.WINDOW_CHUNKS):
            self.tuning.observe(self.review(weak=True))
        self.assertGreater(self.tuning.max_gain(), 30.0)
        self.assertGreater(self.tuning.wake_gain_limit(), 8.0)

    def test_autotune_off_only_observes(self):
        os.environ["ATENA_EAR_AUTOTUNE"] = "0"
        try:
            for _ in range(tuning_module.WINDOW_CHUNKS):
                self.assertEqual(self.tuning.observe(self.review(missed=1)), [])
            self.assertEqual(self.tuning.wake_threshold(), 0.5)
        finally:
            os.environ.pop("ATENA_EAR_AUTOTUNE", None)

    def test_state_survives_restart_and_reset(self):
        for _ in range(tuning_module.WINDOW_CHUNKS):
            self.tuning.observe(self.review(missed=1))
        self.assertEqual(tuning_module.Tuning().wake_threshold(), 0.45)
        tuning_module.TUNING_FILE.unlink()
        self.tuning.load()
        self.assertEqual(self.tuning.wake_threshold(), 0.5)


class RecorderTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        recorder.ROOT = self.dir
        recorder.RECORDS = self.dir / "chunks"
        self.rng = np.random.default_rng(3)

    def run_chunk(self, voiced_ranges, seconds=61.0):
        rec = recorder.Recorder("t")
        now = time.time()
        rec.start = rec.wall = now - seconds
        out = None
        for i in range(int(seconds / recorder.FRAME_S) + 10):
            voiced = any(a <= i < b for a, b in voiced_ranges)
            amp = 0.05 if voiced else 0.003
            frame = (self.rng.standard_normal(recorder.FRAME) * amp).astype(np.float32)
            rms = float(np.sqrt((frame * frame).mean()))
            out = rec.feed(frame, rms, voiced, 0.003, now - seconds + i * recorder.FRAME_S, False, np.ones(8, dtype=np.float32))
            if i == 250:
                rec.note("wake", source="instant")
            if out:
                break
        return out

    def test_only_voiced_stretches_are_kept_with_a_layout(self):
        chunk = self.run_chunk([(200, 400), (1500, 1700)])
        self.assertIsNotNone(chunk)
        self.assertEqual(len(chunk.meta["layout"]), 2)
        self.assertLess(len(chunk.audio) / recorder.RATE, 20)
        self.assertEqual(chunk.meta["events"][0]["kind"], "wake")

    def test_silence_only_chunk_is_discarded(self):
        self.assertIsNone(self.run_chunk([]))

    def test_disabled_recording_stores_nothing(self):
        os.environ["ATENA_EAR_RECORD"] = "0"
        try:
            self.assertIsNone(self.run_chunk([(200, 400)]))
        finally:
            os.environ.pop("ATENA_EAR_RECORD", None)

    def test_write_list_prune_and_purge(self):
        chunk = self.run_chunk([(200, 400)])
        recorder.write_chunk(chunk)
        self.assertEqual(len(recorder.listing()), 1)
        meta_file, meta = recorder.listing()[0]
        self.assertTrue(meta_file.with_suffix(".wav").exists())
        os.environ["ATENA_EAR_RECORD_HOURS"] = "1"
        try:
            meta["started"] = time.time() - 7200
            meta_file.write_text(json.dumps(meta), encoding="utf-8")
            self.assertEqual(recorder.prune(), 1)
        finally:
            os.environ.pop("ATENA_EAR_RECORD_HOURS", None)
        recorder.write_chunk(self.run_chunk([(200, 400)]))
        self.assertEqual(recorder.purge(), 1)
        self.assertEqual(recorder.listing(), [])


class AutoLevelTest(unittest.TestCase):
    @staticmethod
    def tone(level: float) -> np.ndarray:
        return (np.sin(np.arange(480) * 0.3) * level).astype(np.float32)

    @staticmethod
    def rms(frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(frame * frame)))

    def test_amplifies_weak_voice_but_not_silence(self):
        level = AutoLevel()
        voice = self.tone(0.01)
        for _ in range(40):
            out = level.apply(voice, self.rms(voice), 0.001)
        self.assertGreater(float(np.abs(out).max()), float(np.abs(voice).max()) * 4)
        quiet = AutoLevel()
        hiss = (np.random.default_rng(1).standard_normal(480) * 0.001).astype(np.float32)
        for _ in range(40):
            out = quiet.apply(hiss, 0.001, 0.001)
        self.assertTrue(np.array_equal(out, hiss))

    def test_attenuates_a_microphone_that_is_too_loud(self):
        level = AutoLevel()
        loud = self.tone(0.6)
        for _ in range(40):
            out = level.apply(loud, self.rms(loud), 0.001)
        self.assertLess(float(np.abs(out).max()), 0.3)

    def test_never_clips_beyond_full_scale(self):
        level = AutoLevel()
        loud = np.ones(480, dtype=np.float32) * 0.5
        for _ in range(20):
            out = level.apply(loud, 0.5, 0.001)
        self.assertLessEqual(float(np.abs(out).max()), 1.0)

    def test_clipping_voice_asks_once_to_lower_the_microphone(self):
        level = AutoLevel()
        clipped = np.clip(self.tone(1.6), -1.0, 1.0)
        advice = []
        for _ in range(400):
            level.apply(clipped, self.rms(clipped), 0.001)
            advice.append(level.take_advice())
        self.assertEqual([a for a in advice if a], ["lower"])
        self.assertEqual(level.status()["advice"], "lower")

    def test_a_good_level_gives_no_advice_to_act_on(self):
        level = AutoLevel()
        voice = self.tone(0.08)
        advice = []
        for _ in range(400):
            level.apply(voice, self.rms(voice), 0.001)
            advice.append(level.take_advice())
        self.assertEqual([a for a in advice if a], ["ok"])


if __name__ == "__main__":
    unittest.main()
