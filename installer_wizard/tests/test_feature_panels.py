import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAB = re.compile(r'id="tab-([\w-]+)"')


def tabs() -> set[str]:
    pages = list((ROOT / "features").glob("*/admin.html")) + list((ROOT / "web" / "admin").glob("*.html"))
    return {t for page in pages for t in TAB.findall(page.read_text(encoding="utf-8"))}


class FeaturePanelTests(unittest.TestCase):

    def test_every_declared_panel_exists(self):
        known = tabs()
        missing = []
        for manifest in sorted((ROOT / "features").glob("*/feature.json")):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("panel") and data["panel"] not in known:
                missing.append(f"{data['id']} -> {data['panel']}")
        self.assertEqual(missing, [], "feature.json declares a panel without a matching admin tab")

    def test_every_panel_script_registers_its_tab(self):
        for script in sorted((ROOT / "features").glob("*/admin.js")):
            folder = script.parent
            html = folder / "admin.html"
            if not html.exists():
                continue
            for tab in TAB.findall(html.read_text(encoding="utf-8")):
                scripts = "".join(p.read_text(encoding="utf-8") for p in folder.glob("admin*.js"))
                with self.subTest(tab=tab):
                    self.assertTrue(re.search(rf"""\.tab\(\s*["']{re.escape(tab)}["']""", scripts) or "openTab" in scripts or "A.tabs" in scripts,
                                    f"{folder.name}: admin.js does not register tab {tab}")


if __name__ == "__main__":
    unittest.main()
