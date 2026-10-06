import unittest

import licensing
from config import write_env
from features.music import conf, music
from features.voices import catalog


class Base(unittest.TestCase):
    def setUp(self):
        self.addCleanup(write_env, {"ATENA_COMMERCIAL": "0", "ATENA_UNOFFICIAL_SERVICES": "0", "ATENA_VOICE_ONLINE": "0"})


class ModelLicenseTest(Base):
    def test_known_models_map_to_their_licenses(self):
        self.assertEqual(licensing.model_license("granite3.3:2b").name, "Apache-2.0")
        self.assertEqual(licensing.model_license("qwen2.5:7b").name, "Apache-2.0")
        self.assertEqual(licensing.model_license("qwen2.5:3b").name, "Qwen Research License")
        self.assertEqual(licensing.model_license("deepseek-r1:8b").attribution, "Built with Llama")
        self.assertIs(licensing.model_license("misterioso:1b"), licensing.UNKNOWN)

    def test_defaults_are_commercially_safe(self):
        for name in ("granite3.3:2b", "qwen2.5:1.5b", "qwen2.5:0.5b", "qwen2.5:7b", "qwen2.5:14b", "nomic-embed-text"):
            self.assertTrue(licensing.suggested(licensing.model_license(name)), name)

    def test_warnings_explain_restrictions_without_blocking(self):
        eu = licensing.describe(licensing.model_license("llama3.2-vision:11b"))
        self.assertIn("Unione Europea", eu["warning"])
        nc = licensing.describe(licensing.model_license("qwen2.5:3b"))
        self.assertIn("non commerciale", nc["warning"])
        write_env({"ATENA_COMMERCIAL": "1"})
        self.assertIn("in uso commerciale non è consentito", licensing.describe(licensing.model_license("qwen2.5:3b"))["warning"])
        self.assertEqual(licensing.describe(licensing.model_license("granite3.3:2b"))["warnings"], [])


class ComponentTest(Base):
    def test_unofficial_services_need_explicit_acceptance(self):
        write_env({"ATENA_MUSIC_ID": "1", "ATENA_VOICE_ONLINE": "1"})
        self.addCleanup(write_env, {"ATENA_MUSIC_ID": "1"})
        self.assertFalse(music.enabled())
        self.assertFalse(conf.identify())
        self.assertFalse(catalog.online_enabled())
        write_env({"ATENA_UNOFFICIAL_SERVICES": "1"})
        self.assertTrue(music.enabled())
        self.assertTrue(conf.identify())

    def test_commercial_mode_only_changes_automatic_installs(self):
        self.assertTrue(licensing.auto_install("wakeword"))
        write_env({"ATENA_COMMERCIAL": "1"})
        self.assertFalse(licensing.auto_install("wakeword"))
        self.assertFalse(licensing.auto_install("piper_voices"))
        self.assertTrue(licensing.auto_install("speaker_model"))
        write_env({"ATENA_UNOFFICIAL_SERVICES": "1"})
        self.assertTrue(licensing.permitted("shazam"))

    def test_piper_voices_stay_selectable_with_a_warning(self):
        write_env({"ATENA_COMMERCIAL": "1"})
        self.assertTrue(catalog.allowed("it_IT-riccardo-x_low"))
        self.assertTrue(catalog.voice_license("it_IT-riccardo-x_low")["warnings"])

    def test_status_lists_every_component(self):
        state = licensing.status()
        self.assertEqual(set(state["components"]), set(licensing.COMPONENTS))


if __name__ == "__main__":
    unittest.main()
