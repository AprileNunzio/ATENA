import unittest
from server.core.onboarding.hardware_detector import HardwareDetector, HardwareProfile
from server.core.onboarding.setup_wizard import OnboardingWizard

class TestHardwareDetector(unittest.TestCase):
    def test_detect_returns_valid_profile(self):
        detector = HardwareDetector()
        profile = detector.detect()
        self.assertIsInstance(profile, HardwareProfile)
        self.assertGreater(profile.ram_total_gb, 0.0)
        self.assertGreater(profile.cpu_cores, 0)
        self.assertIn(profile.tier, ["high", "mid", "low", "cpu"])
        self.assertEqual(profile.recommended_system1, "qwen2.5:0.5b")
        self.assertIn(profile.system2_quantization, ["Q4", "Q8"])

    def test_wizard_recommendation(self):
        wizard = OnboardingWizard()
        rec_local = wizard.build_recommendation(force_external_api=False)
        self.assertEqual(rec_local.system1_model, "qwen2.5:0.5b")
        self.assertTrue(rec_local.system2_model)

        rec_api = wizard.build_recommendation(force_external_api=True, api_provider="gemini", api_key="test_key")
        self.assertTrue(rec_api.use_external_api)
        self.assertEqual(rec_api.provider, "gemini")
        self.assertEqual(rec_api.api_key, "test_key")

if __name__ == "__main__":
    unittest.main()
