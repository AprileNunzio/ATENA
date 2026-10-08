import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from features.ear import learner as learner_module
from features.people import api, people, voice_training
from state import store


class PlanTest(unittest.TestCase):
    def test_every_language_has_wake_command_and_reading_steps(self):
        for lang in ("it", "en", "fr"):
            kinds = [item["kind"] for item in voice_training.plan(lang)]
            self.assertGreaterEqual(kinds.count("wake"), 5)
            self.assertGreaterEqual(kinds.count("command"), 3)
            self.assertGreaterEqual(kinds.count("reading"), 2)
        self.assertEqual(voice_training.plan("de"), voice_training.plan("it"))

    def test_the_way_a_person_says_the_name_is_extracted(self):
        cases = {"Atena": "atena", "a tena": "atena", "Hey Athena": "athena", "Ehi Adena, che ore sono": "adena",
                 "dis Atèna": "atena"}
        for heard, variant in cases.items():
            with self.subTest(heard=heard):
                self.assertEqual(learner_module.name_variant(heard), variant)
        for heard in ("che ore sono", "la catena", ""):
            with self.subTest(heard=heard):
                self.assertIsNone(learner_module.name_variant(heard))

    def test_steps_are_judged_by_kind(self):
        wake, command, reading = ({"kind": k, "text": t} for k, t in (("wake", "Atena"), ("command", "Atena, che ore sono?"),
                                                                       ("reading", "Il gatto dorme.")))
        self.assertTrue(voice_training.evaluate(wake, "a tena")["ok"])
        self.assertFalse(voice_training.evaluate(wake, "buongiorno")["ok"])
        self.assertTrue(voice_training.evaluate(command, "Adena che ore sono")["ok"])
        self.assertFalse(voice_training.evaluate(command, "Atena accendi la luce")["ok"])
        self.assertTrue(voice_training.evaluate(reading, "il gatto dorme")["ok"])


class LearnerTeachTest(unittest.TestCase):
    def test_a_taught_variant_wakes_at_once(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(learner_module, "LEARN_FILE", Path(tmp) / "l.json"):
            learner = learner_module.Learner()
            self.assertIsNone(learner.find_wake("adina accendi la luce"))
            self.assertTrue(learner.teach("adina"))
            self.assertIsNotNone(learner.find_wake("adina accendi la luce"))
            self.assertFalse(learner.teach("catena"))


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(people, "PEOPLE_DIR", Path(self.tmp.name))
        self.patch.start()
        people.ensure("nunzio", "Nunzio")

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def answers(self):
        plan = voice_training.plan("it")
        heard = {"wake": "a tena", "command": "", "reading": "testo letto"}
        out = []
        for i, item in enumerate(plan):
            said = item["text"] if item["kind"] == "command" else heard[item["kind"]]
            out.append({"index": i, "heard": said, "level": {"rms": 0.07, "peak": 0.99, "clipping": 0.05, "advice": "lower"}})
        return out

    def test_training_builds_the_personal_dictionary(self):
        result = voice_training.record("nunzio", "it", self.answers())
        self.assertEqual(result["wake_variants"], ["atena"])
        self.assertEqual(result["language"], "it")
        self.assertEqual(result["score"], 100)
        self.assertTrue(all(row["heard"] == "a tena" for row in result["dictionary"]))
        self.assertEqual(result["level"]["advice"], "lower")
        self.assertIn("voice_training", json.loads((Path(self.tmp.name) / "nunzio.json").read_text(encoding="utf-8")))

    def test_untrusted_results_are_rejected(self):
        for bad in ([], [{"index": 999, "heard": "x"}], [{"index": "0", "heard": "x"}], "testo", [{"heard": "x"}] * 41):
            with self.subTest(bad=str(bad)[:40]):
                with self.assertRaises(ValueError):
                    voice_training.record("nunzio", "it", bad)
        with self.assertRaises(LookupError):
            voice_training.record("nessuno", "it", self.answers())
        long = voice_training.record("nunzio", "it", [{"index": 0, "heard": "x" * 5000, "level": {"rms": "rotto"}}])
        self.assertLessEqual(len(long["results"][0]["heard"]), voice_training.MAX_TEXT)
        self.assertEqual(long["level"]["rms"], 0.0)

    def test_the_display_saves_and_closes_the_request(self):
        store.voice_training = {"id": "abc", "slug": "nunzio"}
        request = mock.Mock(headers={"content-length": "100"})
        request.json = mock.AsyncMock(return_value={"lang": "it", "answers": self.answers()})
        with mock.patch("features.people.api.require_display"), mock.patch.object(store, "touch"):
            result = asyncio.run(api.display_voice_training_save("nunzio", request))
        self.assertEqual(result["score"], 100)
        self.assertEqual(store.voice_training, {})

    def test_oversized_display_payloads_are_refused(self):
        request = mock.Mock(headers={"content-length": str(api.TRAINING_BODY_LIMIT + 1)})
        with mock.patch("features.people.api.require_display"), self.assertRaises(HTTPException) as caught:
            asyncio.run(api.display_voice_training_save("nunzio", request))
        self.assertEqual(caught.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
