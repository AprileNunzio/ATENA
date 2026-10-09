import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.locale import store as locale_store
from features.people import people
from features.people.presence import PresenceMonitor
from features.voices import languages


class PersonLanguagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(people, "PEOPLE_DIR", Path(self.tmp.name))
        self.patch.start()
        self.prefs = mock.patch.object(locale_store, "PREFS_FILE", Path(self.tmp.name) / "prefs.json")
        self.prefs.start()
        locale_store.store.load()
        locale_store.store._data = {scope: {} for scope in locale_store.SCOPES}
        profile = people.ensure("claire", "Claire")
        profile.update(ui_language="fr", voice_language="fr")
        people.save(profile)

    def tearDown(self):
        self.prefs.stop()
        self.patch.stop()
        self.tmp.cleanup()

    def test_preferences_are_read_from_the_profile(self):
        self.assertEqual(people.preferred_languages("claire"), ("fr", "fr"))
        self.assertEqual(people.preferred_languages("nessuno"), ("", ""))
        self.assertEqual(people.preferred_languages(None), ("", ""))

    def test_ambiguous_speech_uses_the_person_voice_language(self):
        self.assertEqual(languages.resolve("ok", "test-a", None, "claire")["lang"], "fr")
        self.assertEqual(languages.resolve("ok", "test-b", None, "")["lang"], languages.DEFAULT)
        self.assertEqual(languages.resolve("ok", "test-c", None, "klingon")["lang"], languages.DEFAULT)

    def test_clear_speech_in_another_language_still_wins(self):
        heard = languages.resolve("what is the weather like today in London", "test-d", "en", "claire")
        self.assertEqual(heard["lang"], "en")

    def test_presence_carries_the_screen_language_of_known_people(self):
        monitor = PresenceMonitor()
        visible = monitor.with_languages([{"slug": "claire", "known": True}, {"slug": "x", "known": False}])
        self.assertEqual(visible[0]["ui_lang"], "fr")
        self.assertNotIn("ui_lang", visible[1])
        with mock.patch.object(people, "preferred_languages", side_effect=AssertionError("cache")):
            monitor.with_languages([{"slug": "claire", "known": True}])


if __name__ == "__main__":
    unittest.main()
