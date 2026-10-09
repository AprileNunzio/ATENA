import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from features.chat import dialogue as dialogue_module
from features.chat.dialogue import Dialogue
from features.chat.history import HistoryStore


class DialogueHistoryTests(unittest.TestCase):

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = HistoryStore(Path(folder.name) / "dialogue.db")
        patcher = mock.patch.object(dialogue_module, "history", self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_thread_survives_a_restart(self):
        first = Dialogue()
        first.remember("kiosk", "che tempo fa a Roma?", "Sole e 24 gradi.", "weather")
        after_restart = Dialogue()
        self.assertEqual(after_restart.last("kiosk").intent, "weather")
        self.assertEqual(after_restart.resolve("kiosk", "e domani?"), "che tempo fa a Roma domani?")
        self.assertIn("Sole e 24 gradi.", after_restart.context("kiosk"))

    def test_devices_are_separate_and_old_turns_are_not_reloaded(self):
        self.store.add("kiosk", "vecchio", "risposta", "chat", time.time() - 3600)
        self.store.add("telefono", "ciao", "ciao a te", "chat", time.time())
        fresh = Dialogue()
        self.assertEqual(fresh.recent("kiosk"), [])
        self.assertEqual([t.text for t in fresh.recent("telefono")], ["ciao"])

    def test_a_broken_database_keeps_working_in_memory(self):
        broken = HistoryStore(Path(tempfile.gettempdir()) / "non" / "esiste" / "\0bad.db")
        with mock.patch.object(dialogue_module, "history", broken):
            d = Dialogue()
            d.remember("kiosk", "ciao", "ciao!", "chat")
            self.assertEqual(d.last("kiosk").reply, "ciao!")
        self.assertTrue(broken.broken)

    def test_history_can_be_forgotten(self):
        Dialogue().remember("kiosk", "segreto", "ok", "chat")
        self.assertEqual(self.store.forget("kiosk"), 1)
        self.assertEqual(Dialogue().recent("kiosk"), [])


if __name__ == "__main__":
    unittest.main()
