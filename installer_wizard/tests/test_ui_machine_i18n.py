import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import UI_LANGUAGES

from features.locale import machine as module
from features.locale.machine import MachineCatalog, valid


class ValidTest(unittest.TestCase):
    def test_placeholders_and_sizes(self):
        self.assertTrue(valid("Pagina {0} di {1}", "Página {0} de {1}"))
        self.assertFalse(valid("Pagina {0} di {1}", "Página de"))
        self.assertFalse(valid("Ciao", ""))
        self.assertFalse(valid("Ciao", "x" * 100))
        self.assertFalse(valid("Ciao", 3))

    def test_every_extra_language_has_a_name(self):
        self.assertTrue(set(module.EXTRA) <= set(UI_LANGUAGES))
        self.assertNotIn("it", module.EXTRA)
        self.assertTrue(module.RTL & set(module.EXTRA))


ROWS = [("Salva", "Save"), ("Pagina {0}", "Page {0}"), ("Annulla", "Cancel")]


class CatalogTest(unittest.IsolatedAsyncioTestCase):
    async def test_batch_keeps_only_valid_translations_and_view_reports_progress(self):
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(module, "CACHE_DIR", Path(root)), mock.patch.object(module, "sources", return_value=ROWS):
            catalog = MachineCatalog()
            reply = {"t": ["Guardar", "Página", "Cancelar"]}
            with mock.patch("features.brain.llm.generate", mock.AsyncMock(return_value=reply)):
                view = catalog.view("es")
                self.assertTrue(view["running"])
                await catalog.jobs["es"]
            view = catalog.view("es")
            self.assertEqual((view["done"], view["total"]), (2, 3))
            self.assertIn(["Save", "Guardar"], view["pairs"])
            self.assertNotIn("Pagina {0}", catalog.load("es"))

    async def test_wrong_length_answer_is_ignored_and_unknown_language_rejected(self):
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(module, "CACHE_DIR", Path(root)), mock.patch.object(module, "sources", return_value=ROWS):
            catalog = MachineCatalog()
            with mock.patch("features.brain.llm.generate", mock.AsyncMock(return_value={"t": ["solo uno"]})):
                self.assertEqual(await catalog._batch("de", ROWS), {})
            with self.assertRaises(KeyError):
                catalog.view("xx")
            with self.assertRaises(KeyError):
                catalog.view("it")


if __name__ == "__main__":
    unittest.main()
