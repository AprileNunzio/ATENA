import sys
import unittest
from pathlib import Path

import numpy as np

BIO = Path(__file__).resolve().parents[1] / "features" / "biometrics"
if str(BIO) not in sys.path:
    sys.path.append(str(BIO))

import embeddings as emb
import liveness as lv

RNG = np.random.default_rng(11)
DIM = 64


def person(seed: int, n: int = 12, noise: float = 0.15) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.standard_normal(DIM)
    return emb.unit_rows(base + rng.standard_normal((n, DIM)) * noise * np.abs(base).mean() * 4)


def sibling(of: np.ndarray, seed: int, closeness: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    centre = emb.centroid(of)
    other = emb.unit(centre * closeness + emb.unit(rng.standard_normal(DIM)) * (1 - closeness))
    return emb.unit_rows(other + rng.standard_normal((len(of), DIM)) * 0.04)


class EmbeddingMathTest(unittest.TestCase):
    def test_unit_vectors_and_centroid(self):
        v = emb.unit(np.array([3.0, 4.0]))
        self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0)
        self.assertAlmostEqual(float(np.linalg.norm(emb.centroid(person(1)))), 1.0)
        self.assertEqual(emb.unit_rows(np.ones(4)).shape, (1, 4))
        self.assertEqual(float(np.linalg.norm(emb.unit(np.zeros(3)))), 0.0)

    def test_prune_keeps_the_most_diverse_and_the_newest_sample(self):
        base = person(2, 6)
        duplicates = np.vstack([base, base[0] + 1e-4, base[0] + 2e-4, base[1] + 1e-4])
        kept = emb.prune(duplicates, 6)
        self.assertEqual(len(kept), 6)
        newest = emb.unit(duplicates[-1])
        self.assertTrue(any(np.allclose(row, newest, atol=1e-5) for row in kept))
        spread_before = float(np.mean(emb.redundancy(duplicates)))
        self.assertLess(float(np.mean(emb.redundancy(kept))), spread_before)

    def test_merge_respects_the_limit_and_handles_empty(self):
        self.assertEqual(len(emb.merge(None, person(3, 5), 40)), 5)
        self.assertEqual(len(emb.merge(person(3, 30), person(3, 30), 40)), 40)
        self.assertEqual(len(emb.merge(np.zeros((0, DIM)), person(3, 4), 10)), 4)

    def test_threshold_is_base_with_few_samples_and_bounded_otherwise(self):
        self.assertEqual(emb.person_threshold(person(4, 3), 0.4), 0.4)
        tight = emb.person_threshold(person(4, 20, 0.05), 0.4)
        loose = emb.person_threshold(person(4, 20, 1.5), 0.4)
        for t in (tight, loose):
            self.assertGreaterEqual(t, 0.4 - emb.THRESHOLD_FLOOR_DELTA - 1e-9)
            self.assertLessEqual(t, 0.4 + emb.THRESHOLD_CEIL_DELTA + 1e-9)
        self.assertGreaterEqual(tight, loose)

    def test_twin_detection_flags_look_alikes_only(self):
        a, b, c = person(5), person(6), None
        twin = sibling(a, 7, 0.97)
        cents = {"anna": emb.centroid(a), "bruno": emb.centroid(b), "alba": emb.centroid(twin)}
        pairs = emb.twin_pairs(cents, 0.8)
        self.assertEqual(pairs, {frozenset(("anna", "alba"))})
        self.assertIsNone(c)


class DecisionTest(unittest.TestCase):
    thresholds = {"a": 0.4, "b": 0.4}

    def test_clear_match_unknown_and_empty(self):
        ok = emb.decide({"a": 0.8, "b": 0.1}, self.thresholds, 0.4, 0.05, 0.12, set())
        self.assertEqual((ok["slug"], ok["ambiguous"], ok["reason"]), ("a", False, "ok"))
        low = emb.decide({"a": 0.3, "b": 0.1}, self.thresholds, 0.4, 0.05, 0.12, set())
        self.assertEqual((low["slug"], low["reason"]), (None, "sotto soglia"))
        self.assertEqual(emb.decide({}, {}, 0.4, 0.05, 0.12, set())["slug"], None)

    def test_close_second_makes_the_result_ambiguous(self):
        r = emb.decide({"a": 0.62, "b": 0.60}, self.thresholds, 0.4, 0.05, 0.12, set())
        self.assertEqual((r["slug"], r["ambiguous"]), (None, True))

    def test_twins_need_a_larger_margin_than_strangers(self):
        scores = {"a": 0.70, "b": 0.62}
        normal = emb.decide(scores, self.thresholds, 0.4, 0.05, 0.12, set())
        twins = emb.decide(scores, self.thresholds, 0.4, 0.05, 0.12, {frozenset(("a", "b"))})
        self.assertEqual(normal["slug"], "a")
        self.assertTrue(twins["ambiguous"])
        wide = emb.decide({"a": 0.80, "b": 0.62}, self.thresholds, 0.4, 0.05, 0.12, {frozenset(("a", "b"))})
        self.assertEqual(wide["slug"], "a")

    def test_a_far_second_never_blocks(self):
        r = emb.decide({"a": 0.55, "b": 0.10}, self.thresholds, 0.4, 0.05, 0.12, {frozenset(("a", "b"))})
        self.assertEqual(r["slug"], "a")

    def test_per_person_threshold_is_used(self):
        r = emb.decide({"a": 0.45}, {"a": 0.5}, 0.4, 0.05, 0.12, set())
        self.assertIsNone(r["slug"])

    def test_fusion_blends_when_both_and_flags_disagreement(self):
        fused, conflict = emb.fuse({"a": 0.8, "b": 0.3}, {"a": 0.6, "b": 0.2}, 0.35, 0.4)
        self.assertAlmostEqual(fused["a"], 0.65 * 0.8 + 0.35 * 0.6)
        self.assertFalse(conflict)
        fused, conflict = emb.fuse({"a": 0.8, "b": 0.3}, {"a": 0.2, "b": 0.7}, 0.35, 0.4)
        self.assertTrue(conflict)
        self.assertEqual(emb.decide(fused, {}, 0.4, 0.05, 0.12, set(), conflict)["ambiguous"], True)

    def test_weak_infrared_disagreement_is_not_a_conflict(self):
        _, conflict = emb.fuse({"a": 0.8, "b": 0.3}, {"b": 0.25}, 0.35, 0.4)
        self.assertFalse(conflict)

    def test_people_without_infrared_samples_keep_their_rgb_score(self):
        fused, _ = emb.fuse({"a": 0.8, "b": 0.7}, {"a": 0.7}, 0.35, 0.4)
        self.assertEqual(fused["b"], 0.7)
        self.assertEqual(emb.fuse({"a": 0.5}, None, 0.35)[0], {"a": 0.5})

    def test_realistic_twin_scenario_separates_with_samples_and_stays_cautious_with_one_probe(self):
        anna = person(20, 16, 0.05)
        alba = sibling(anna, 21, 0.9)
        probe = anna[0]
        scores = {"anna": emb.score_against(anna, probe), "alba": emb.score_against(alba, probe)}
        twins = emb.twin_pairs({"anna": emb.centroid(anna), "alba": emb.centroid(alba)}, 0.7)
        verdict = emb.decide(scores, {"anna": 0.4, "alba": 0.4}, 0.4, 0.05, 0.12, twins)
        self.assertIn(verdict["slug"], ("anna", None))
        self.assertNotEqual(verdict["slug"], "alba")


def textured_face(size=60, level=120, contrast=40, centre=1.4, seed=0):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size]
    falloff = 1 + (centre - 1) * np.exp(-(((x - size / 2) ** 2 + (y - size / 2) ** 2) / (2 * (size / 3) ** 2)))
    image = level * falloff + rng.standard_normal((size, size)) * contrast
    return np.clip(image, 0, 255).astype(np.uint8)


class LivenessTest(unittest.TestCase):
    def frame_with(self, patch, at=(40, 30)):
        gray = np.full((200, 300), 25, dtype=np.uint8)
        h, w = patch.shape
        gray[at[1]:at[1] + h, at[0]:at[0] + w] = patch
        return gray, (at[0], at[1], w, h)

    def test_real_face_stats_beat_a_flat_dark_screen(self):
        real_gray, real_box = self.frame_with(textured_face())
        flat_gray, flat_box = self.frame_with(np.full((60, 60), 12, dtype=np.uint8))
        real = lv.stats_score(lv.metrics(real_gray, real_box))
        flat = lv.stats_score(lv.metrics(flat_gray, flat_box))
        self.assertGreater(real, 0.6)
        self.assertLess(flat, 0.25)

    def test_overexposed_and_tiny_regions(self):
        blown = np.full((100, 100), 255, dtype=np.uint8)
        self.assertLess(lv.stats_score(lv.metrics(blown, (0, 0, 100, 100))), 0.2)
        gray, _ = self.frame_with(blown)
        self.assertIsNone(lv.metrics(gray, (0, 0, 5, 5)))

    def test_box_agreement_tolerates_offset_and_rejects_far_or_wrong_size(self):
        near = lv.box_agreement((100, 80, 80, 80), (640, 480), (50, 40, 40, 40), (320, 240))
        shifted = lv.box_agreement((100, 80, 80, 80), (640, 480), (80, 70, 40, 40), (320, 240))
        far = lv.box_agreement((100, 80, 80, 80), (640, 480), (250, 150, 40, 40), (320, 240))
        small = lv.box_agreement((100, 80, 80, 80), (640, 480), (60, 50, 8, 8), (320, 240))
        self.assertGreater(near, 0.8)
        self.assertGreater(near, shifted)
        self.assertLess(far, 0.1)
        self.assertLess(small, 0.1)
        learned = lv.box_agreement((100, 80, 80, 80), (640, 480), (80, 70, 40, 40), (320, 240), offset=(0.1, 0.1))
        self.assertGreater(learned, shifted)

    def test_without_a_sensor_the_state_is_unknown_never_spoof(self):
        self.assertEqual(lv.assess(False, False, None, 0, None, 0.55), {"state": "unknown", "score": None, "parts": {}})

    def test_face_missing_in_infrared_is_a_spoof(self):
        r = lv.assess(True, False, None, 0.0, None, 0.55)
        self.assertEqual((r["state"], r["score"]), ("spoof", 0.0))

    def test_real_face_with_matching_infrared_is_live(self):
        gray, box = self.frame_with(textured_face())
        r = lv.assess(True, True, lv.metrics(gray, box), 0.9, 0.6, 0.55)
        self.assertEqual(r["state"], "live")
        self.assertGreater(r["score"], 0.75)
        self.assertEqual(set(r["parts"]), {"presence", "agreement", "stats", "support"})

    def test_found_but_flat_and_unsupported_is_rejected(self):
        gray, box = self.frame_with(np.full((60, 60), 14, dtype=np.uint8))
        r = lv.assess(True, True, lv.metrics(gray, box), 0.5, 0.05, 0.55)
        self.assertEqual(r["state"], "spoof")

    def test_missing_gallery_support_is_neutral_not_penalised(self):
        gray, box = self.frame_with(textured_face())
        with_support = lv.assess(True, True, lv.metrics(gray, box), 0.9, None, 0.55)
        self.assertNotIn("support", with_support["parts"])
        self.assertEqual(with_support["state"], "live")

    def test_smoothing(self):
        self.assertEqual(lv.smooth(None, 0.8), 0.8)
        self.assertAlmostEqual(lv.smooth(0.0, 1.0, 0.25), 0.25)


if __name__ == "__main__":
    unittest.main()
