import json
import re
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
from features.nexus.domain.zones import classify

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "web" / "admin" / "admin.html"
ZONES_JS = ROOT / "web" / "nexus" / "features" / "shell" / "zones.js"
TOOL_JS = ROOT / "web" / "nexus" / "features" / "tool" / "tool.js"
HEADERS = {"X-Atena-Request": "1"}


class NexusParityTest(unittest.TestCase):
    def test_every_classic_section_is_reachable_from_nexus(self):
        classic_tabs = set(re.findall(r'data-tab="([a-z0-9_-]+)"', ADMIN.read_text(encoding="utf-8"))) - {"feature"}
        linked = set(re.findall(r'\["([a-z0-9_/-]+)", "', ZONES_JS.read_text(encoding="utf-8")))
        self.assertEqual(classic_tabs - linked, set(), "aggiungi queste schede a «classic» in web/nexus/features/shell/zones.js")

    def test_every_feature_tab_belongs_to_a_feature_with_a_full_panel(self):
        panels = {json.loads(p.read_text(encoding="utf-8")).get("panel") for p in (ROOT / "features").glob("*/feature.json")}
        for html in (ROOT / "features").glob("*/admin.html"):
            for tab in re.findall(r'id="tab-([a-z0-9_-]+)"', html.read_text(encoding="utf-8")):
                self.assertIn(tab, panels, f"{html.parent.name}: la scheda «{tab}» non è collegata a nessun manifest")
        tool = TOOL_JS.read_text(encoding="utf-8")
        self.assertIn('{ id: "full", label: "Pannello completo", min: "explorer" }', tool)
        self.assertIn("classicFrame(`f/${tool.id}`", tool)

    def test_every_feature_has_a_zone(self):
        for path in (ROOT / "features").glob("*/feature.json"):
            self.assertTrue(classify(json.loads(path.read_text(encoding="utf-8"))).zone)

    def test_classic_panel_can_be_embedded_only_by_itself(self):
        with mock.patch("setup_api.done", return_value=True):
            r = TestClient(atena_supervisor.admin).get("/")
        self.assertEqual(r.headers["content-security-policy"], "frame-ancestors 'self'")
        self.assertEqual(r.headers["x-frame-options"], "SAMEORIGIN")
        self.assertIn("/static/admin/embed.js", r.text)
        with mock.patch("setup_api.done", return_value=True):
            nexus = TestClient(atena_supervisor.admin).get("/nexus")
        self.assertIn("frame-src 'self'", nexus.headers["content-security-policy"])


if __name__ == "__main__":
    unittest.main()
