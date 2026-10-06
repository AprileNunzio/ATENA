import asyncio
import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

import numpy as np

EAR = Path(__file__).resolve().parents[1] / "features" / "ear"
if str(EAR) not in sys.path:
    sys.path.append(str(EAR))

SCRIPT = {"text": "Atena accendi la luce"}
fake = types.ModuleType("stt")
fake.lock = None
fake.calls = 0


def transcribe_segments(audio, name="same", offset=0.0):
    fake.calls += 1
    return [{"start": round(offset + 0.2, 2), "end": round(offset + 2.0, 2), "text": SCRIPT["text"]}]


fake.transcribe_segments = transcribe_segments
sys.modules["stt"] = fake

import learner as learner_module
import recorder
import reviewer as reviewer_module
import tuning as tuning_module


class ReviewerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        recorder.ROOT = self.dir
        recorder.RECORDS = self.dir / "chunks"
        reviewer_module.REVIEWS = self.dir / "reviews.jsonl"
        reviewer_module.SUMMARY = self.dir / "summary.json"
        tuning_module.TUNING_FILE = self.dir / "tuning.json"
        learner_module.LEARN_FILE = self.dir / "learn.json"
        reviewer_module.tuning.state.update(wake_threshold=None, wake_gain=1.0, max_gain=None)
        reviewer_module.tuning.state["window"] = dict(tuning_module.FRESH)
        self.rng = np.random.default_rng(5)
        fake.lock = asyncio.Lock()
        fake.calls = 0
        SCRIPT["text"] = "Atena accendi la luce"

    def chunk(self, events):
        rec = recorder.Recorder("t")
        now = time.time()
        rec.start = rec.wall = now - 61
        for i in range(2100):
            voiced = 200 <= i < 300
            amp = 0.05 if voiced else 0.003
            frame = (self.rng.standard_normal(recorder.FRAME) * amp).astype(np.float32)
            rms = float(np.sqrt((frame * frame).mean()))
            out = rec.feed(frame, rms, voiced, 0.003, now - 61 + i * recorder.FRAME_S, False, None)
            if out:
                out.meta["events"] = events
                return out
        raise AssertionError("nessun blocco prodotto")

    def run_review(self, events, busy=False):
        recorder.write_chunk(self.chunk(events))
        rv = reviewer_module.Reviewer(lambda: busy)
        reviewer_module.activity.last_voice = time.time() - 1000
        meta_file, meta = recorder.listing()[0]
        asyncio.run(rv.review(meta_file, meta))
        return rv

    def test_missed_wake_is_found_stored_and_summarised(self):
        self.run_review([{"kind": "heard", "t": 6.5, "text": "giarbis accendi"}])
        rows = reviewer_module.recent_reviews(10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["missed"], 1)
        summary = json.loads(reviewer_module.SUMMARY.read_text(encoding="utf-8"))
        self.assertEqual(summary["summary"]["chunks"], 1)
        self.assertEqual(summary["pending"], 0)
        self.assertTrue(summary["recording"])

    def test_reviewed_chunk_is_marked_and_not_picked_twice(self):
        self.run_review([{"kind": "wake", "t": 6.5, "source": "instant"}])
        meta = recorder.listing()[0][1]
        self.assertTrue(meta["reviewed"])
        self.assertEqual(reviewer_module.recent_reviews(10)[0]["true_wakes"], 1)

    def test_agreement_is_measured_against_live_transcript(self):
        SCRIPT["text"] = "accendi la luce in cucina"
        self.run_review([{"kind": "transcript", "t": 7.0, "dur": 2.0, "text": "accendi la luce"}])
        row = reviewer_module.recent_reviews(10)[0]
        self.assertEqual(row["checked"], 1)
        self.assertGreater(row["agreement"], 0.5)
        self.assertLess(row["agreement"], 1.0)

    def test_review_stops_when_someone_is_speaking(self):
        recorder.write_chunk(self.chunk([]))
        rv = reviewer_module.Reviewer(lambda: True)
        meta_file, meta = recorder.listing()[0]
        asyncio.run(rv.review(meta_file, meta))
        self.assertEqual(reviewer_module.recent_reviews(10), [])
        self.assertFalse(recorder.listing()[0][1].get("reviewed"))
        self.assertEqual(fake.calls, 0)

    def test_audio_is_deleted_right_away_when_retention_is_zero(self):
        import os
        os.environ["ATENA_EAR_KEEP_REVIEWED_H"] = "0"
        try:
            self.run_review([])
        finally:
            os.environ.pop("ATENA_EAR_KEEP_REVIEWED_H", None)
        self.assertEqual(recorder.listing(), [])
        self.assertEqual(len(reviewer_module.recent_reviews(10)), 1)


if __name__ == "__main__":
    unittest.main()
