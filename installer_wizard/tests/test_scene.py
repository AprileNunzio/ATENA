import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from features.scene import voice
from features.scene.fusion import PresenceFusion
from features.scene.graph import SceneError, SceneGraph, inside

T0 = datetime(2026, 10, 6, 8, 0).timestamp()
TABLE = [[0.0, 0.5], [0.5, 0.5], [0.5, 1.0], [0.0, 1.0]]
SHELF = [[0.6, 0.0], [1.0, 0.0], [1.0, 0.4], [0.6, 0.4]]


class GraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = [T0]
        self.g = SceneGraph(Path(self.tmp.name) / "s.db", clock=lambda: self.now[0])
        self.addCleanup(self.g.close)
        self.table = self.g.save_anchor({"name": "tavolo della cucina", "room": "cucina", "polygon": TABLE, "x": 2.1, "y": 0.4, "z": 0.75})
        self.shelf = self.g.save_anchor({"name": "mensola ingresso", "room": "ingresso", "polygon": SHELF, "entrance": True})
        self.keys = self.g.save_item({"name": "chiavi della Grande Punto", "labels": ["telecomando"], "aliases": ["chiavi"]})
        self.wallet = self.g.save_item({"name": "portafoglio", "labels": ["borsa"]})

    def see(self, label, box, held=False):
        return self.g.observe("main", [{"label": label, "score": 0.8, "box": box, "held": held}], (640, 480), "Nunzio")

    def test_point_in_polygon(self):
        self.assertTrue(inside((0.25, 0.75), TABLE))
        self.assertFalse(inside((0.75, 0.75), TABLE))

    def test_validation(self):
        for body in ({"name": "x", "polygon": [[0, 0], [1, 1]]}, {"name": "x", "polygon": [[0, 0], [2, 0], [0, 1]]},
                     {"name": "<script>", "polygon": TABLE}, {"name": "x", "polygon": TABLE, "x": "nan?"}, {"name": "x", "polygon": TABLE, "source": "../etc"}):
            with self.subTest(body=body), self.assertRaises(SceneError):
                self.g.save_anchor(body)
        with self.assertRaises(SceneError):
            self.g.save_item({"name": "x", "labels": []})
        with self.assertRaises(SceneError):
            self.g.save_profile({"name": "uscita", "requirements": [{"item": "nope"}]})

    def test_objects_are_located_on_anchors_with_coordinates(self):
        self.assertEqual(self.see("telecomando", [100, 300, 40, 40]), 1)
        seen = self.g.last_seen(["telecomando"])
        self.assertEqual((seen["anchor_name"], seen["room"]), ("tavolo della cucina", "cucina"))
        self.assertEqual(seen["position"], {"x": 2.1, "y": 0.4, "z": 0.75})
        self.assertEqual(self.see("telecomando", [100, 300, 40, 40]), 0)
        self.now[0] += 5
        self.see("telecomando", [500, 50, 40, 40], held=True)
        seen = self.g.last_seen(["telecomando"])
        self.assertTrue(seen["held"])
        self.assertEqual(seen["holder"], "Nunzio")

    def test_readiness_profile(self):
        profile = self.g.save_profile({"name": "uscita", "aliases": ["uscire"], "requirements": [
            {"item": self.keys["id"], "near_entrance": True, "max_age_min": 60}, {"item": self.wallet["id"], "anchor": self.shelf["id"]}]})
        result = self.g.readiness(profile)
        self.assertFalse(result["ready"])
        self.assertEqual([c["status"] for c in result["checks"]], ["unknown", "unknown"])
        self.see("telecomando", [100, 300, 40, 40])
        self.see("borsa", [500, 50, 40, 40])
        self.assertEqual([c["status"] for c in self.g.readiness(profile)["checks"]], ["elsewhere", "ok"])
        self.now[0] += 40
        self.see("telecomando", [520, 60, 30, 30])
        self.assertTrue(self.g.readiness(profile)["ready"])
        self.now[0] += 2 * 3600
        self.assertEqual(self.g.readiness(profile)["checks"][0]["status"], "stale")

    def test_voice_answers_in_both_languages(self):
        self.see("telecomando", [100, 300, 40, 40])
        it = voice.answer("Atena, dov'è le chiavi della Grande Punto?", self.g, "it", T0 + 120)
        self.assertIn("tavolo della cucina", it)
        self.assertIn("2.1", it)
        en = voice.answer("where are the chiavi?", self.g, "en", T0 + 120)
        self.assertIn("kitchen", en.replace("tavolo della cucina", "kitchen"))
        self.assertIn("ago", en)
        self.g.save_profile({"name": "uscita", "aliases": ["uscire"], "requirements": [{"item": self.keys["id"], "near_entrance": True}]})
        self.assertIn("Non ancora", voice.answer("è tutto pronto per uscire?", self.g, "it", T0 + 120))
        self.assertIsNone(voice.answer("accendi la luce", self.g))

    def test_graph_export(self):
        self.see("telecomando", [100, 300, 40, 40])
        graph = self.g.export()
        self.assertIn({"from": f"item:{self.keys['id']}", "to": f"anchor:{self.table['id']}", "relation": "on", "at": T0}, graph["edges"])
        self.assertIn({"id": "room:cucina", "type": "room", "name": "cucina"}, graph["nodes"])


class FusionTest(unittest.TestCase):
    def setUp(self):
        self.now = [T0]
        self.sent = []
        self.f = PresenceFusion(lambda t, p, r: self.sent.append((t, p)), clock=lambda: self.now[0], names=lambda: {"nunzio": "Nunzio Aprile"})

    def person(self, confidence, state="live"):
        return {"people": [{"slug": "nunzio", "name": "Nunzio", "known": True, "confidence": confidence, "liveness": {"state": state}}]}

    def topics(self):
        return [t for t, _ in self.sent]

    def test_face_and_voice_fuse_into_an_arrival(self):
        self.f.on_vision(self.person(0.6))
        self.f.step()
        self.assertNotIn("fusion.arrival", self.topics())
        self.f.on_voice({"speaker": "nunzio", "known": True, "score": 0.9})
        snap = self.f.step()
        self.assertIn("fusion.arrival", self.topics())
        self.assertEqual(snap["people"][0]["sources"], ["face", "voice"])

    def test_spoofed_face_is_not_enough(self):
        self.f.on_vision(self.person(0.99, "spoof"))
        self.f.step()
        self.assertNotIn("fusion.arrival", self.topics())

    def test_evidence_decays_into_a_departure(self):
        self.f.on_vision(self.person(0.95))
        self.f.step()
        self.assertIn("fusion.arrival", self.topics())
        self.now[0] += 600
        self.f.step()
        self.assertIn("fusion.departure", self.topics())

    def test_home_tracker_maps_person_entities(self):
        self.f.on_home({"entity_id": "person.nunzio", "to": "home"})
        self.f.step()
        self.assertIn("fusion.arrival", self.topics())
        self.f.on_home({"entity_id": "person.nunzio", "to": "not_home"})
        self.f.step()
        self.assertIn("fusion.departure", self.topics())


if __name__ == "__main__":
    unittest.main()
