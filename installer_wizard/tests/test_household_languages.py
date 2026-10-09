import asyncio
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

from features.locale import household
from features.locale import store as locale_store
from features.people import people
from tests.test_locale import LocaleBase

SPEC = importlib.util.spec_from_file_location("langpick", Path(__file__).resolve().parents[1] / "features" / "ear" / "langpick.py")
langpick = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(langpick)


class LangPickTests(unittest.TestCase):

    def test_short_italian_mistaken_for_portuguese_stays_italian(self):
        probs = [("pt", 0.48), ("it", 0.40), ("es", 0.10), ("en", 0.02)]
        self.assertEqual(langpick.pick(probs, "it", ["it", "en"], 0.75), "it")

    def test_clear_english_is_accepted_when_the_house_speaks_it(self):
        probs = [("en", 0.85), ("it", 0.10), ("de", 0.05)]
        self.assertEqual(langpick.pick(probs, "it", ["it", "en"], 0.75), "en")
        self.assertEqual(langpick.pick(probs, "it", ["it", "fr"], 0.75), "it")

    def test_without_a_list_the_old_threshold_applies(self):
        self.assertEqual(langpick.pick([("fr", 0.9)], "it", [], 0.75), "fr")
        self.assertEqual(langpick.pick([("fr", 0.5)], "it", [], 0.75), "it")
        self.assertEqual(langpick.allowed("it, EN,xx1, ;rm"), ["it", "en"])


class HouseholdTests(LocaleBase):

    def test_household_collects_system_profiles_and_choices(self):
        claire = people.ensure("claire", "Claire")
        claire.update(voice_language="fr")
        people.save(claire)
        locale_store.store.put("devices", "cucina", reply="de")
        self.assertEqual(household.household(), ["de", "fr", "it"])

    def test_sync_writes_only_when_languages_change(self):
        written = {}
        with mock.patch.object(household, "env_get", side_effect=lambda k, d="": written.get(k, d)), \
                mock.patch.object(household, "write_env", side_effect=written.update), \
                mock.patch.object(household.sys, "platform", "win32"):
            self.assertTrue(asyncio.run(household.sync()))
            self.assertFalse(asyncio.run(household.sync()))
        self.assertEqual(written["ATENA_EAR_LANGUAGES"], "it")


if __name__ == "__main__":
    unittest.main()
