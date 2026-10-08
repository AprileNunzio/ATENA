import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

EAR = Path(__file__).resolve().parents[1] / "features" / "ear"
if str(EAR) not in sys.path:
    sys.path.append(str(EAR))

import learner as learner_module


class WakeNameTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = Path(self.dir.name) / "learn.json"
        self.old = learner_module.LEARN_FILE
        learner_module.LEARN_FILE = self.file

    def tearDown(self):
        learner_module.LEARN_FILE = self.old
        self.dir.cleanup()

    def test_ehi_atena_wakes_and_leaves_the_command(self):
        learner = learner_module.Learner()
        for text in ("Ehi, Atena, accendi la luce", "ehi atena accendi la luce", "Atena accendi la luce",
                     "Hey Athena, accendi la luce"):
            with self.subTest(text=text):
                start, end, _ = learner.find_wake(text)
                self.assertEqual(text[end:], "accendi la luce")

    def test_split_name_and_more_greetings_wake_and_leave_the_command(self):
        learner = learner_module.Learner()
        for text in ("a tena, accendi la luce", "Ate na accendi la luce", "Hei Atena accendi la luce",
                     "E Atena, accendi la luce", "Eh atena accendi la luce"):
            with self.subTest(text=text):
                found = learner.find_wake(text)
                self.assertIsNotNone(found)
                self.assertEqual(text[found[1]:], "accendi la luce")
        for text in ("la tenda è rotta", "e la catena del cancello"):
            with self.subTest(text=text):
                self.assertIsNone(learner.find_wake(text))

    def test_close_mishearing_wakes_but_common_words_do_not(self):
        learner = learner_module.Learner()
        self.assertIsNotNone(learner.find_wake("Atene accendi la luce"))
        for text in ("catena del cancello", "arena di Verona", "Serena accendi la luce"):
            with self.subTest(text=text):
                self.assertIsNone(learner.find_wake(text))
        self.assertFalse(learner.learn_variant("catena"))

    def test_variants_learned_for_another_name_are_dropped(self):
        self.file.write_text(json.dumps({"variants": {"marvin": 5}, "strict": False}), encoding="utf-8")
        learner = learner_module.Learner()
        self.assertEqual(learner.data["variants"], {})
        self.assertIsNone(learner.find_wake("marvin accendi la luce"))
        self.assertEqual(learner.hotwords().split()[0], "Atena")

    def test_wake_model_name_is_validated(self):
        import importlib
        os.environ["ATENA_WAKEWORD_MODEL"] = "../../etc/passwd"
        try:
            wakeword = importlib.import_module("wakeword")
            self.assertEqual(wakeword.model_name(), "ehi_atena")
            os.environ["ATENA_WAKEWORD_MODEL"] = "ehi_atena_v2"
            self.assertEqual(wakeword.model_name(), "ehi_atena_v2")
        finally:
            os.environ.pop("ATENA_WAKEWORD_MODEL", None)


if __name__ == "__main__":
    unittest.main()
