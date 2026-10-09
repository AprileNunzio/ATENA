import unittest

from features.voices import languages


@unittest.skipIf(languages.NATIVE is None, "atena_native not built")
class NativeLanguageTests(unittest.TestCase):

    def test_rust_detector_handles_replies_the_vocabulary_misses(self):
        self.assertEqual(languages.detect("Ho acceso Luce studio e chiuso le tapparelle.", "en"), "it")
        self.assertEqual(languages.detect("Ich habe das Licht im Arbeitszimmer eingeschaltet.", "it"), "de")
        self.assertEqual(languages.detect("Liczba pi to stała matematyczna, która opisuje okrąg.", "it"), "pl")

    def test_short_or_uncertain_text_keeps_the_default(self):
        self.assertEqual(languages.detect("ok", "fr"), "fr")
        self.assertIsNone(languages.detect_native("ciao"))

    def test_allowlist_is_respected(self):
        self.assertIn(languages.detect_native("I turned on the light in the study.", "en,fr"), ("en", "fr", None))


if __name__ == "__main__":
    unittest.main()
