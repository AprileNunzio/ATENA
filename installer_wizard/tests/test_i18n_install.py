import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "i18n"))
import extract  # noqa: E402

CATALOG = json.loads((ROOT / "web" / "shared" / "i18n_catalog.json").read_text(encoding="utf-8"))
SURFACES = ("web/monitor/", "web/setup/", "web/screen/", "web/shared/", "backend/")
SLOT = re.compile(r"\{\d+\}")

SAFE_KEYS = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const body = html.match(/const TEXT = (\{[\s\S]*?\n  \});/)[1];
const TEXT = Function(`return ${body}`)();
const shape = (o) => Object.keys(o).sort().map((k) => typeof o[k] === "object" ? `${k}:{${shape(o[k])}}` : k).join(",");
console.log(JSON.stringify(Object.fromEntries(Object.entries(TEXT).map(([lang, t]) => [lang, shape(t)]))));
"""


def install_strings() -> list[str]:
    same = set(CATALOG["same"])
    return sorted(s for s, files in extract.extract().items()
                  if s not in same and any(f.startswith(SURFACES) for f in files))


class InstallScreensTest(unittest.TestCase):
    def test_install_and_update_screens_speak_english_and_french(self):
        english = {p[0] for p in CATALOG["pairs"]}
        french = {p[0] for p in CATALOG.get("fr", [])}
        strings = install_strings()
        self.assertGreater(len(strings), 300)
        self.assertEqual([s for s in strings if s not in english], [], "add the English translation to «pairs»")
        self.assertEqual([s for s in strings if s not in french], [], "add the French translation to «fr» as [italian, french]")

    def test_step_titles_and_phase_messages_are_part_of_the_install_screens(self):
        strings = set(install_strings())
        for expected in ("Analisi del sistema", "Servizi cognitivi", "Verifica: {0}", "Tutti i sistemi operativi",
                         "Cerco una versione più recente online…"):
            self.assertIn(expected, strings)

    def test_french_placeholders_match(self):
        for source, target in CATALOG.get("fr", []):
            with self.subTest(source=source):
                self.assertEqual(sorted(SLOT.findall(source)), sorted(SLOT.findall(target)))

    @unittest.skipUnless(shutil.which("node"), "node is required to read the safe mode page")
    def test_safe_mode_page_has_every_text_in_every_language(self):
        with tempfile.TemporaryDirectory() as root:
            script = Path(root) / "keys.js"
            script.write_text(SAFE_KEYS, encoding="utf-8")
            out = subprocess.run(["node", str(script), str(ROOT / "web" / "safe" / "safe.html")],
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        shapes = json.loads(out.stdout)
        self.assertEqual(set(shapes), {"it", "en", "fr"})
        self.assertEqual(len(set(shapes.values())), 1, shapes)


if __name__ == "__main__":
    unittest.main()
