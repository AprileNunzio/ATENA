import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.locale import service
from features.locale import store as locale_store
from features.people import people
from features.voices import languages


class LocaleBase(unittest.TestCase):

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for target, name, value in ((people, "PEOPLE_DIR", self.root / "people"),
                                    (locale_store, "PREFS_FILE", self.root / "locale" / "prefs.json")):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        (self.root / "people").mkdir()
        locale_store.store._data = {scope: {} for scope in locale_store.SCOPES}
        profile = people.ensure("anna", "Anna")
        profile.update(ui_language="", voice_language="it")
        people.save(profile)

    def restart(self) -> None:
        locale_store.store._data = {scope: {} for scope in locale_store.SCOPES}
        locale_store.store.load()


class ReplyLanguageTests(LocaleBase):

    def test_a_spoken_switch_is_remembered_for_the_person_after_a_restart(self):
        first = languages.resolve("Parlami in inglese per favore", "kiosk", None, "anna")
        self.assertEqual((first["lang"], first["switched"]), ("en", True))
        self.restart()
        later = languages.resolve("ciao come stai", "kiosk", "it", "anna")
        self.assertEqual((later["lang"], later["sticky"]), ("en", True))

    def test_the_choice_follows_the_person_on_every_device(self):
        languages.resolve("parliamo in francese", "kiosk", None, "anna")
        self.assertEqual(languages.resolve("ok", "telefono", None, "anna")["lang"], "fr")

    def test_an_unknown_speaker_changes_only_that_device(self):
        languages.resolve("speak in spanish", "cucina", None, "")
        self.assertEqual(languages.resolve("hola", "cucina", None, "")["lang"], "es")
        self.assertEqual(languages.resolve("ok", "salotto", None, "")["lang"], languages.DEFAULT)
        self.assertEqual(languages.resolve("ok", "cucina", None, "anna")["lang"], "it")

    def test_teacher_mode_is_remembered_and_can_be_stopped(self):
        languages.resolve("insegnami il tedesco", "kiosk", None, "anna")
        self.restart()
        self.assertEqual(languages.resolve("ok", "kiosk", None, "anna"), {"lang": "de", "teach": True, "sticky": True, "switched": False})
        stop = languages.resolve("basta parlare in tedesco", "kiosk", None, "anna")
        self.assertEqual((stop["lang"], stop["sticky"]), ("it", False))
        self.assertIsNone(service.chosen("anna", "kiosk"))

    def test_corrupted_preferences_fall_back_safely(self):
        locale_store.PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        locale_store.PREFS_FILE.write_text("{rotto", encoding="utf-8")
        self.restart()
        self.assertIsNone(service.chosen("anna", "kiosk"))


class ScreenLanguageTests(LocaleBase):

    def test_each_admin_user_keeps_its_own_screen_language(self):
        service.set_ui("fr", user="nunzio")
        service.set_ui("en", user="maria")
        self.restart()
        self.assertEqual(service.ui_lang(user="nunzio"), "fr")
        self.assertEqual(service.ui_lang(user="maria"), "en")
        self.assertEqual(service.ui_lang(user="sconosciuto"), service.system_ui())

    def test_person_choice_wins_over_device_and_is_stored_in_the_profile(self):
        service.set_ui("en", device="kiosk")
        service.set_ui("fr", person="anna")
        self.assertEqual(service.ui_lang(device="kiosk"), "en")
        self.assertEqual(service.ui_lang(device="kiosk", person="anna"), "fr")
        self.assertEqual(people.load("anna")["ui_language"], "fr")

    def test_unsupported_values_are_rejected(self):
        with self.assertRaises(ValueError):
            service.set_ui("klingon", device="kiosk")
        with self.assertRaises(ValueError):
            locale_store.store.put("devices", "../../etc", ui="it")


if __name__ == "__main__":
    unittest.main()
