import asyncio
import re
import unittest
from pathlib import Path
from unittest import mock

from features.chat import wake
from features.chat.wake_phrases import PHRASES
from features.locale import service
from features.voices import languages

ROOT = Path(__file__).resolve().parents[1]
ITALIAN = re.compile(r"\b(Eccomi|signore|sistemi|operativi|Come posso aiutarla)\b")


def env(values: dict):
    return mock.patch.object(service, "env_get", lambda key, default="": values.get(key, default))


class DefaultLanguageTest(unittest.TestCase):
    def test_reply_language_follows_the_system_language(self):
        with env({"ATENA_UI_LANG": "fr"}):
            self.assertEqual(service.system_reply(), "fr")
        with env({"ATENA_UI_LANG": "fr", "ATENA_REPLY_LANG": "en"}):
            self.assertEqual(service.system_reply(), "en")
        with env({}):
            self.assertEqual(service.system_reply(), "it")
        with env({"ATENA_UI_LANG": "xx"}):
            self.assertEqual(service.system_reply(), languages.DEFAULT)

    def test_unrecognised_short_text_is_answered_in_the_system_language(self):
        with env({"ATENA_UI_LANG": "fr"}), mock.patch.object(service, "chosen", return_value=None):
            self.assertEqual(languages.resolve("ok", "kiosk")["lang"], "fr")


class WakeGreetingTest(unittest.TestCase):
    def run_greeting(self, lang: str) -> dict:
        async def nothing(*_args, **_kwargs):
            return None
        with mock.patch.object(wake, "_next_event", nothing), mock.patch.object(wake, "_weather", nothing), \
                mock.patch.object(wake.speaker, "name", return_value=""):
            return asyncio.run(wake.greeting(lang))

    def test_french_greeting_is_french(self):
        result = self.run_greeting("fr")
        text = result["reply"] + " " + result["card"]["text"] + " " + " ".join(i["label"] for i in result["card"]["items"])
        self.assertNotRegex(text, ITALIAN)
        self.assertIn("monsieur", result["reply"])
        self.assertEqual(result["lang"], "fr")

    def test_every_language_table_is_complete(self):
        keys = set(PHRASES["it"])
        for lang, table in PHRASES.items():
            self.assertEqual(set(table), keys, lang)
            for opener in table["openers"]:
                self.assertIn("{who}", opener)

    def test_other_languages_are_translated_with_a_time_limit(self):
        async def slow(text, lang, force=False):
            await asyncio.sleep(10)
            return text
        with mock.patch.object(wake, "TRANSLATE_SECONDS", 0.05), \
                mock.patch("features.locale.pivot.pivot.from_pivot", slow):
            result = self.run_greeting("de")
        self.assertTrue(result["reply"])


class ExpertToggleTest(unittest.TestCase):
    def test_toggle_lives_in_the_top_bar_and_hints_are_clickable(self):
        script = (ROOT / "web" / "admin" / "uimode.js").read_text(encoding="utf-8")
        self.assertIn('document.querySelector(".topbar .row")', script)
        self.assertIn("data-ui-mode-set", script)
        brain = (ROOT / "features" / "brain" / "admin.html").read_text(encoding="utf-8")
        self.assertIn('data-ui-mode-set="expert"', brain)


if __name__ == "__main__":
    unittest.main()
