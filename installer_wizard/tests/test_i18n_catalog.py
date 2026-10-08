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
SLOT = re.compile(r"\{\d+\}")


class CatalogTest(unittest.TestCase):
    def test_every_visible_string_is_translated(self):
        self.maxDiff = None
        known = {p[0] for p in CATALOG["pairs"]} | {p[0] for p in CATALOG["reverse"]} | set(CATALOG["same"])
        missing = sorted(s for s in extract.extract() if s not in known)
        self.assertEqual(missing, [], "add these strings to web/shared/i18n_catalog.json: Italian ones to «pairs» as "
                                      "[italian, english], English ones to «reverse» as [english, italian]")

    def test_placeholders_match(self):
        for it, en in CATALOG["pairs"] + CATALOG["reverse"]:
            with self.subTest(it=it):
                self.assertEqual(sorted(SLOT.findall(it)), sorted(SLOT.findall(en)))

    def test_no_source_has_two_translations(self):
        for table in ("pairs", "reverse"):
            seen: dict[str, str] = {}
            for source, target in CATALOG[table]:
                if source in seen and seen[source] != target:
                    self.fail(f"«{source}» translates to both «{seen[source]}» and «{target}»")
                seen[source] = target


RUNNER = r"""
const fs = require("fs");
const catalog = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const results = {};
for (const lang of ["en", "it", "fr"]) {
  const g = { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: lang }, ATENA_UI_LANG: lang,
    document: { readyState: "complete", documentElement: { lang }, body: null, addEventListener() {}, dispatchEvent() {} },
    fetch: async () => ({ json: async () => catalog }), CustomEvent: function () {} };
  const source = fs.readFileSync(process.argv[3], "utf8");
  new Function("window", "document", "localStorage", "navigator", "fetch", "CustomEvent", "NodeFilter", source)
    (g, g.document, g.localStorage, g.navigator, g.fetch, g.CustomEvent, {});
  results[lang] = g;
}
setTimeout(() => {
  const t = (lang, s) => results[lang].AtenaI18n.translate(s);
  console.log(JSON.stringify({
    exact: t("en", "Aggiungi stampante"),
    spaced: t("en", "  Salva profilo \n"),
    pattern: t("en", "Pagina 3 di 9 · 120 modelli totali"),
    reverse: t("it", "Autonomous checking off"),
    untouched: t("en", "Mario Rossi"),
    french: t("fr", "Analisi del sistema"),
    nestedEn: t("en", "Verifica: Analisi del sistema"),
    nestedFr: t("fr", "Verifica: Analisi del sistema"),
  }));
}, 50);
"""


@unittest.skipUnless(shutil.which("node"), "node is required to test the browser translator")
class RuntimeTranslatorTest(unittest.TestCase):
    def test_exact_patterns_whitespace_and_reverse(self):
        with tempfile.TemporaryDirectory() as root:
            script = Path(root) / "run.js"
            script.write_text(RUNNER, encoding="utf-8")
            out = subprocess.run(["node", str(script), str(ROOT / "web" / "shared" / "i18n_catalog.json"),
                                  str(ROOT / "web" / "shared" / "translate.js")], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["exact"], "Add printer")
        self.assertEqual(data["spaced"], "  Save profile \n")
        self.assertEqual(data["pattern"], "Page 3 of 9 · 120 models in total")
        self.assertEqual(data["reverse"], "Valutazione automatica disattivata")
        self.assertEqual(data["untouched"], "Mario Rossi")
        self.assertEqual(data["french"], "Analyse du système")
        self.assertEqual(data["nestedEn"], "Checking: System analysis")
        self.assertEqual(data["nestedFr"], "Vérification : Analyse du système")


if __name__ == "__main__":
    unittest.main()
