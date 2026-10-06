import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

EAR = Path(__file__).resolve().parents[1] / "features" / "ear"
if str(EAR) not in sys.path:
    sys.path.append(str(EAR))

import voiceprint
from features.biometrics import embeddings as emb

DIM = 192


def voice(seed, n=10, noise=0.05):
    rng = np.random.default_rng(seed)
    base = rng.standard_normal(DIM)
    return emb.unit_rows(base + rng.standard_normal((n, DIM)) * noise * np.abs(base).mean() * 4)


def twin_of(rows, seed, share=0.5):
    return emb.unit_rows(emb.centroid(rows) * (1 - share) + voice(seed, len(rows), 0.05) * share)


class VoiceprintTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(voiceprint, "STORE", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.vp = voiceprint.Voiceprints.__new__(voiceprint.Voiceprints)
        self.vp.extractor = object()
        self.vp.lock = threading.Lock()
        self.vp.samples, self.vp.centres, self.vp.limits, self.vp.twins, self.vp.stamp = {}, {}, {}, set(), 0.0

    def enrol(self, slug, rows):
        for row in rows:
            self.vp.add(slug, row, "lettura")

    def test_known_speaker_unknown_speaker_and_empty_gallery(self):
        self.assertEqual(self.vp.identify(voice(1)[0]), (None, 0.0))
        anna = voice(1)
        self.enrol("anna", anna)
        self.enrol("bruno", voice(2))
        slug, score = self.vp.identify(anna[3])
        self.assertEqual(slug, "anna")
        self.assertGreater(score, 0.9)
        self.assertIsNone(self.vp.identify(voice(99)[0])[0])
        self.assertEqual(self.vp.identify(None), (None, 0.0))

    def test_similar_voices_need_a_wider_margin(self):
        anna = voice(1, 14)
        alba = twin_of(anna, 5, 0.6)
        self.enrol("anna", anna)
        self.enrol("alba", alba)
        self.assertIn(frozenset(("anna", "alba")), self.vp.twins)
        self.assertEqual(self.vp.identify(anna[2])[0], "anna")
        self.assertEqual(self.vp.identify(alba[2])[0], "alba")
        halfway = emb.unit(emb.centroid(anna) + emb.centroid(alba))
        self.assertIsNone(self.vp.identify(halfway)[0])
        self.assertTrue(self.vp.verdict(halfway)["ambiguous"])

    def test_report_lists_enrolment_threshold_and_similar_pairs(self):
        anna = voice(1, 14)
        self.enrol("anna", anna)
        self.enrol("alba", twin_of(anna, 5, 0.6))
        report = json.loads((self.dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(set(report["people"]), {"anna", "alba"})
        self.assertTrue(report["people"]["anna"]["enrolled"])
        self.assertEqual(report["people"]["anna"]["similar"][0]["slug"], "alba")
        self.assertIn("threshold", report["people"]["anna"])

    def test_automatic_learning_never_adds_a_different_voice(self):
        anna = voice(1, 8)
        self.enrol("anna", anna)
        before = self.vp.count("anna")
        stranger = voice(77, 1)[0]
        self.assertEqual(self.vp.add("anna", stranger, "ascolto"), before)
        self.assertEqual(self.vp.count("anna"), before)
        own = emb.unit(anna[0] + np.random.default_rng(3).standard_normal(DIM) * 0.01)
        self.assertGreater(self.vp.add("anna", own, "ascolto"), before)

    def test_bootstrapping_accepts_the_first_samples_then_gets_selective(self):
        rows = voice(1, 6)
        for row in rows[:4]:
            self.assertGreater(self.vp.add("anna", row, "ascolto"), 0)
        self.assertLess(self.vp.count("anna"), voiceprint.ENROLLED_AT)

    def test_ambiguous_probe_is_not_learned_automatically(self):
        anna = voice(1, 14)
        alba = twin_of(anna, 5, 0.6)
        self.enrol("anna", anna)
        self.enrol("alba", alba)
        before = self.vp.count("anna")
        halfway = emb.unit(emb.centroid(anna) + emb.centroid(alba))
        self.vp.add("anna", halfway, "ascolto")
        self.assertEqual(self.vp.count("anna"), before)

    def test_improvement_can_be_switched_off(self):
        anna = voice(1, 8)
        self.enrol("anna", anna)
        before = self.vp.count("anna")
        with mock.patch.dict(os.environ, {"ATENA_VOICE_AUTOIMPROVE": "0"}):
            self.vp.add("anna", anna[0], "ascolto")
            self.assertEqual(self.vp.count("anna"), before)
            self.assertGreater(self.vp.add("anna", anna[1], "lettura"), 0)

    def test_samples_are_kept_diverse_and_bounded(self):
        anna = voice(1, 10)
        self.enrol("anna", anna)
        rng = np.random.default_rng(4)
        for i in range(60):
            self.vp.add("anna", emb.unit(anna[i % 10] + rng.standard_normal(DIM) * 0.02), "lettura")
        self.assertLessEqual(self.vp.count("anna"), voiceprint.MAX_SAMPLES)
        self.assertEqual(self.vp.count("anna"), voiceprint.MAX_SAMPLES)

    def test_invalid_names_and_forgetting(self):
        self.assertEqual(self.vp.add("../x", voice(1)[0], "lettura"), 0)
        self.assertEqual(self.vp.add("anna", None, "lettura"), 0)
        self.enrol("anna", voice(1))
        self.vp.forget("anna")
        self.assertEqual(self.vp.count("anna"), 0)
        self.assertFalse((self.dir / "anna.npy").exists())

    def test_adaptive_threshold_can_be_disabled(self):
        self.enrol("anna", voice(1, 14, 0.5))
        adaptive = self.vp.limits["anna"]
        with mock.patch.dict(os.environ, {"ATENA_VOICE_ADAPTIVE": "0"}):
            self.vp._load()
            self.assertEqual(self.vp.limits["anna"], voiceprint.match_base())
        self.assertNotEqual(adaptive, voiceprint.match_base())


if __name__ == "__main__":
    unittest.main()
