import asyncio
import unittest

from features.agent import commands, paths, tools_files
from features.shares import archive


class ShareFilesTest(unittest.TestCase):
    def setUp(self):
        archive.ensure()
        self.file = archive.path("scambio") / "Preventivo Cliente.txt"
        self.file.write_text("totale 100 euro", encoding="utf-8")

    def tearDown(self):
        self.file.unlink(missing_ok=True)

    def test_folder_names_point_into_the_share(self):
        for raw in ("Scambio/Preventivo Cliente.txt", "05 Scambio/Preventivo Cliente.txt", "scambio/Preventivo Cliente.txt"):
            with self.subTest(raw=raw):
                self.assertEqual(paths.resolve(raw), self.file.resolve())

    def test_bare_name_falls_back_to_share_root(self):
        self.assertEqual(paths.resolve("05 Scambio"), archive.path("scambio").resolve())
        self.assertEqual(paths.resolve("nota.txt"), (paths.FILES / "nota.txt").resolve())

    def test_find_is_case_insensitive_and_covers_the_whole_share(self):
        found = asyncio.run(tools_files.find_files("preventivo"))
        self.assertIn(str(self.file), found)

    def test_read_and_modify(self):
        self.assertIn("100 euro", asyncio.run(tools_files.read_file("Scambio/Preventivo Cliente.txt")))
        asyncio.run(tools_files.write_file("Scambio/Preventivo Cliente.txt", "totale 120 euro"))
        self.assertEqual(self.file.read_text(encoding="utf-8"), "totale 120 euro")

    def test_missing_file_suggests_search(self):
        self.assertIn("find_files", asyncio.run(tools_files.read_file("Scambio/nessuno.txt")))

    def test_share_requests_reach_the_agent(self):
        for text in ("leggi il pdf nella cartella scambio", "trovami il preventivo in scambio", "modifica il docx in scambio"):
            with self.subTest(text=text):
                self.assertTrue(commands.WEAK.search(text))


if __name__ == "__main__":
    unittest.main()
