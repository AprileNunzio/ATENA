import unittest

from features.voices import speech_rules


class SpeechRulesTests(unittest.TestCase):

    def test_each_language_reads_units_in_its_own_words(self):
        text = "Fuori ci sono 21°C, umidità 60% e vento a 15 km/h alle 7:30."
        self.assertIn("21 gradi", speech_rules.normalize(text, "it"))
        self.assertIn("60 percent", speech_rules.normalize(text, "en"))
        self.assertIn("15 Kilometer pro Stunde", speech_rules.normalize(text, "de"))
        self.assertIn("7 heures 30", speech_rules.normalize(text, "fr"))
        self.assertIn("21 grados", speech_rules.normalize(text, "es"))

    def test_links_and_markdown_are_never_read_aloud(self):
        self.assertEqual(speech_rules.normalize("**Vedi** https://example.com/x", "en"), "Vedi the link")
        self.assertEqual(speech_rules.normalize("A.T.E.N.A. — ciao", "ja"), "Atena, ciao")


if __name__ == "__main__":
    unittest.main()
