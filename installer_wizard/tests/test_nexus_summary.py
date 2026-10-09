import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import atena_supervisor
from features.nexus.application.summary_service import SummaryService
from features.nexus.domain import summary
from features.nexus.domain.zones import FAMILIES, ZONES, classify

HEADERS = {"X-Atena-Request": "1"}
FEATURES = Path(__file__).resolve().parents[1] / "features"


def inputs(**overrides) -> summary.Inputs:
    base = dict(phase="READY", progress=100.0, steps={}, step_titles={}, components={}, features=[], update={}, approvals=0)
    return summary.Inputs(**{**base, **overrides})


class ZonesTest(unittest.TestCase):
    def test_every_shipped_feature_lands_in_a_valid_place(self):
        for path in FEATURES.glob("*/feature.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            placement = classify(manifest)
            self.assertIn(placement.zone, ZONES, manifest["id"])
            self.assertEqual(placement.zone == "tools", placement.family in FAMILIES, manifest["id"])
            self.assertIn(placement.level, ("explorer", "pilot", "architect"))

    def test_known_features_and_manifest_overrides(self):
        self.assertEqual(classify({"id": "vision"}).as_dict(), {"zone": "tools", "family": "perception", "level": "explorer"})
        self.assertEqual(classify({"id": "firewall"}).zone, "network")
        self.assertEqual(classify({"id": "proxmox"}).level, "architect")
        self.assertEqual(classify({"id": "x_new", "category": "casa"}).family, "home")
        self.assertEqual(classify({"id": "x", "zone": "trust", "family": "home"}).as_dict(), {"zone": "trust", "family": "", "level": "pilot"})
        self.assertEqual(classify({"id": "x", "zone": "nowhere", "family": "bogus", "level": "god"}).as_dict(),
                         {"zone": "tools", "family": "productivity", "level": "pilot"})


class SummaryDomainTest(unittest.TestCase):
    def test_tone_follows_phase_and_components(self):
        self.assertEqual(summary.tone(inputs(phase="INSTALLING")), "busy")
        self.assertEqual(summary.tone(inputs()), "ok")
        self.assertEqual(summary.tone(inputs(components={"core": {"status": "down"}})), "bad")
        self.assertEqual(summary.tone(inputs(components={"voice": {"status": "down", "on_demand": True}})), "ok")
        self.assertEqual(summary.tone(inputs(phase="DEGRADED")), "warn")

    def test_health_ignores_on_demand_parts(self):
        comps = {"a": {"status": "ok"}, "b": {"status": "warn"}, "c": {"status": "down", "on_demand": True}}
        self.assertEqual(summary.health(comps), 75)
        self.assertEqual(summary.health({}), 100)

    def test_todos_are_sorted_by_severity_and_capped(self):
        data = inputs(components={"core": {"status": "down", "label": "Atena Core"}, "disk": {"status": "warn", "label": "Archiviazione"}},
                      steps={"docker": {"status": "failed"}}, step_titles={"docker": "Motore container"},
                      update={"available": True}, approvals=2,
                      features=[{"id": "nvr", "name": "NVR", "state": {"risk": True}}])
        items = summary.todos(data)
        self.assertEqual([t.severity for t in items], ["bad", "bad", "warn", "warn", "warn", "info"])
        self.assertIn("«Atena Core» non funziona", items[0].text)
        self.assertIn("2 approvazioni in attesa", [t.text for t in items])
        self.assertIn("f/nvr", [t.target for t in items])
        many = inputs(steps={f"s{i}": {"status": "failed"} for i in range(20)})
        self.assertEqual(len(summary.todos(many)), summary.MAX_TODOS)

    def test_headline_speaks_both_languages_of_the_levels(self):
        self.assertIn("63 strumenti, 50 attivi", summary.headline(inputs(), 50, 63)["pilot"])
        self.assertIn("1 cosa da controllare", summary.headline(inputs(phase="DEGRADED"), 1, 1)["pilot"])
        self.assertTrue(summary.headline(inputs(phase="BOOTING"), 0, 0)["explorer"])


class SummaryServiceTest(unittest.TestCase):
    def test_build_merges_state_catalog_and_placement(self):
        service = SummaryService(
            state=lambda: {"phase": "READY", "components": {"core": {"status": "ok", "label": "Atena Core"}}},
            catalog=lambda: {"features": [{"id": "vision", "name": "Visione", "toggle": {"env": "X"},
                                           "state": {"enabled": True, "mode": "auto"}},
                                          {"id": "proxmox", "name": "Proxmox", "state": {"enabled": False, "mode": "0"}}]},
            step_titles=dict, approvals=lambda: 0)
        data = service.build()
        self.assertEqual(data["counts"]["total"], 2)
        self.assertEqual(data["counts"]["active"], 1)
        vision = next(t for t in data["tools"] if t["id"] == "vision")
        self.assertEqual((vision["zone"], vision["family"], vision["level"], vision["toggle"]), ("tools", "perception", "explorer", True))
        self.assertEqual(data["components"][0]["label"], "Atena Core")


class SummaryApiTest(unittest.TestCase):
    def test_summary_requires_session_and_lists_tools(self):
        self.assertEqual(TestClient(atena_supervisor.admin).get("/api/nexus/summary").status_code, 401)
        admin = TestClient(atena_supervisor.admin)
        self.assertEqual(admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS).status_code, 200)
        data = admin.get("/api/nexus/summary").json()
        self.assertGreater(data["counts"]["total"], 30)
        self.assertTrue({"tone", "health", "headline", "todos", "families", "tools"} <= set(data))
        self.assertNotIn("values", data["tools"][0])


if __name__ == "__main__":
    unittest.main()
