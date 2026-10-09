import unittest
from unittest.mock import patch

from features.brain import brains as brains_module
from features.brain import presets, scope

LOCAL_A, LOCAL_B = "qwen2.5:1.5b", "qwen2.5:7b"
SERVER = "cloud:srv-studio/llama3.1:8b"
CLOUD = "cloud:openai/gpt-5"
CLOUD_FAST = "cloud:openai/gpt-5-mini"


def fake_origin(ref):
    return {SERVER: scope.SERVER, CLOUD: scope.CLOUD, CLOUD_FAST: scope.CLOUD}.get(ref, scope.LOCAL)


class ScopeTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(scope, "origin", side_effect=fake_origin)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_anywhere_keeps_the_order(self):
        self.assertEqual(scope.apply([CLOUD, LOCAL_A, SERVER], "anywhere"), [CLOUD, LOCAL_A, SERVER])

    def test_home_never_reaches_the_cloud(self):
        self.assertEqual(scope.apply([CLOUD, LOCAL_A, SERVER], "home"), [LOCAL_A, SERVER])

    def test_home_first_moves_cloud_last_keeping_relative_order(self):
        self.assertEqual(scope.apply([CLOUD_FAST, CLOUD, LOCAL_A, SERVER], "home_first"),
                         [LOCAL_A, SERVER, CLOUD_FAST, CLOUD])

    def test_fastest_prefers_measured_speed_and_demotes_failing(self):
        stats = {LOCAL_A: {"ok": 5, "fail": 0, "avg_ms": 900}, LOCAL_B: {"ok": 5, "fail": 0, "avg_ms": 300},
                 SERVER: {"ok": 1, "fail": 4, "avg_ms": 100}}
        self.assertEqual(scope.apply([SERVER, LOCAL_A, CLOUD, LOCAL_B], "anywhere", "fastest", stats),
                         [LOCAL_B, LOCAL_A, CLOUD, SERVER])

    def test_unknown_values_fall_back(self):
        self.assertEqual(scope.clean_scope("x"), "anywhere")
        self.assertEqual(scope.clean_strategy(None), "order")


class PrivateUrlTest(unittest.TestCase):
    def test_lan_and_public(self):
        for url in ("http://192.168.1.50:1234/v1", "localhost:11434", "http://studio.local:8000", "10.0.0.2"):
            self.assertTrue(scope.private_url(url), url)
        for url in ("https://api.openai.com/v1", "http://8.8.8.8"):
            self.assertFalse(scope.private_url(url), url)


CATALOG = {
    "local": {"models": [{"ref": LOCAL_B, "size_gb": 4.7, "installed": True},
                         {"ref": LOCAL_A, "size_gb": 1.0, "installed": True},
                         {"ref": "phi4:14b", "size_gb": 9.1, "installed": False}]},
    "servers": [{"online": True, "models": [{"ref": SERVER}]}, {"online": False, "models": [{"ref": "cloud:srv-x/m"}]}],
    "cloud": [{"default": "gpt-5", "models": [{"ref": CLOUD}, {"ref": CLOUD_FAST}]}],
}


class PresetTest(unittest.TestCase):
    def test_private_uses_only_home_sources(self):
        order, scope_value = presets.plan("private", "deep", CATALOG)
        self.assertEqual((order, scope_value), ([LOCAL_B, LOCAL_A, SERVER], "home"))

    def test_chat_prefers_small_and_fast_models(self):
        order, _ = presets.plan("smart", "chat", CATALOG)
        self.assertEqual(order, [CLOUD_FAST, LOCAL_A, LOCAL_B, SERVER])

    def test_balanced_puts_cloud_last(self):
        order, scope_value = presets.plan("balanced", "deep", CATALOG)
        self.assertEqual((order[-1], scope_value), (CLOUD, "home_first"))

    def test_auto_clears_the_list(self):
        self.assertEqual(presets.plan("auto", "deep", CATALOG), ([], "anywhere"))

    def test_impossible_preset_explains_why(self):
        with self.assertRaisesRegex(presets.PresetError, "cloud"):
            presets.plan("cloud", "deep", {**CATALOG, "cloud": []})
        with self.assertRaises(presets.PresetError):
            presets.plan("nope", "deep", CATALOG)


class EffectiveChainTest(unittest.TestCase):
    def test_role_scope_filters_the_runtime_chain(self):
        env = {"ATENA_LLM_DEEP_ORDER": f"{CLOUD},{LOCAL_B}", "ATENA_LLM_DEEP_SCOPE": "home"}
        with patch.object(brains_module, "read_env", return_value=env), \
                patch.object(scope, "origin", side_effect=fake_origin):
            b = brains_module.Brains()
            cfg = b.config()
            self.assertEqual(cfg["deep_scope"], "home")
            self.assertEqual(cfg["deep_profile"], "custom")
            self.assertEqual(b.effective("deep", cfg), [LOCAL_B])
            self.assertEqual(cfg["deep"], [CLOUD, LOCAL_B])


if __name__ == "__main__":
    unittest.main()
