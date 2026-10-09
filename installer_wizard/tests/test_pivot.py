import asyncio
import unittest
from collections import OrderedDict
from unittest import mock

from features.brain.llm import BrainUnavailable
from features.chat import assistant
from features.locale.pivot import Pivot

TRANSLATIONS = {
    "turn on the light": "accendi la luce",
    "Ho acceso Luce studio.": "I turned on the study light.",
    "allume la lumière": "accendi la luce",
}


async def fake_generate(text, **kwargs):
    return TRANSLATIONS.get(text, text)


class PivotTests(unittest.TestCase):

    def setUp(self):
        self.pivot = Pivot()

    def test_italian_passes_through_without_calls(self):
        with mock.patch("features.brain.llm.generate", side_effect=AssertionError("no call")):
            self.assertEqual(asyncio.run(self.pivot.to_pivot("accendi la luce", "it")), "accendi la luce")
            self.assertEqual(asyncio.run(self.pivot.from_pivot("Fatto", "it")), "Fatto")

    def test_requests_are_translated_and_cached(self):
        with mock.patch("features.brain.llm.generate", side_effect=fake_generate) as generate:
            self.assertEqual(asyncio.run(self.pivot.to_pivot("turn on the light", "en")), "accendi la luce")
            asyncio.run(self.pivot.to_pivot("turn on the light", "en"))
        self.assertEqual(generate.call_count, 1)

    def test_replies_already_in_the_target_language_are_kept(self):
        with mock.patch("features.brain.llm.generate", side_effect=AssertionError("no call")):
            reply = "The weather today is sunny and warm, you can go out without an umbrella."
            self.assertEqual(asyncio.run(self.pivot.from_pivot(reply, "en")), reply)

    def test_no_model_means_original_text(self):
        with mock.patch("features.brain.llm.generate", side_effect=BrainUnavailable("giù")):
            self.assertEqual(asyncio.run(self.pivot.to_pivot("turn on the light", "en")), "turn on the light")


class AssistantPivotTests(unittest.TestCase):

    def run_handle(self, text, lang, switched=False):
        seen = {}

        async def route(routing, core_call, speech_lang):
            seen["routing"] = routing
            return {"reply": "Ho acceso Luce studio.", "intent": "home"}

        async def core_call(query):
            return {"query": query}

        with mock.patch.object(assistant, "_route", side_effect=route), \
                mock.patch("features.brain.llm.generate", side_effect=fake_generate), \
                mock.patch.object(assistant.pivot, "cache", OrderedDict()):
            result = asyncio.run(assistant.handle(text, core_call, {"lang": lang, "switched": switched}))
        return result, seen

    def test_english_request_uses_italian_skills_and_answers_in_english(self):
        result, seen = self.run_handle("turn on the light", "en")
        self.assertEqual(seen["routing"], "accendi la luce")
        self.assertEqual(result["reply"], "I turned on the study light.")

    def test_model_replies_already_in_english_are_not_retranslated(self):
        async def route(routing, core_call, speech_lang):
            data = await core_call(routing)
            return {"reply": f"Sure, here is the answer about {data['query']} and the weather today.", "intent": "conversation"}

        async def core_call(query):
            return {"query": query}

        with mock.patch.object(assistant, "_route", side_effect=route),                 mock.patch("features.brain.llm.generate", side_effect=fake_generate) as generate:
            result = asyncio.run(assistant.handle("what is new", core_call, {"lang": "en"}))
        self.assertIn("what is new", result["reply"])
        self.assertEqual(generate.call_count, 1)

    def test_french_request_is_routed_too(self):
        _, seen = self.run_handle("allume la lumière", "fr")
        self.assertEqual(seen["routing"], "accendi la luce")

    def test_language_switch_requests_are_not_translated(self):
        _, seen = self.run_handle("speak english to me", "en", switched=True)
        self.assertEqual(seen["routing"], "speak english to me")


if __name__ == "__main__":
    unittest.main()
