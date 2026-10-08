import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.core.orchestrator import brain_routing
from server.features.llm_gateway import tuning
from server.features.llm_gateway.contracts import LLMMessage, LLMRequest


class CoreTuningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "routes.json"
        self.patch = patch.object(brain_routing.settings, "BRAIN_ROUTES_PATH", str(self.path))
        self.patch.start()
        brain_routing._cache = (-1, {})

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def publish(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        brain_routing._cache = (-1, {})

    def request(self, component: str) -> LLMRequest:
        return LLMRequest(model_name="m", messages=[LLMMessage(role="user", content="ciao")], component=component,
                          system_prompt="Base")

    def test_agent_parameters_are_applied_to_core_requests(self):
        self.publish({"tuning": {"research": {"temperature": 0.9, "max_tokens": 900, "instructions": "Cita le fonti"}}})
        tuned = tuning.apply(self.request("research"))
        self.assertEqual((tuned.temperature, tuned.max_tokens), (0.9, 900))
        self.assertTrue(tuned.system_prompt.startswith("Base"))
        self.assertIn("Cita le fonti", tuned.system_prompt)
        untouched = tuning.apply(self.request("domotics"))
        self.assertEqual((untouched.temperature, untouched.max_tokens, untouched.system_prompt), (0.2, 2048, "Base"))

    def test_out_of_range_values_are_clamped_never_trusted(self):
        self.publish({"tuning": {"research": {"temperature": 99, "max_tokens": -5, "instructions": "x" * 5000}}})
        tuned = tuning.apply(self.request("research"))
        self.assertEqual((tuned.temperature, tuned.max_tokens), (1.5, 64))
        self.assertLessEqual(len(tuned.system_prompt), len("Base") + 2 + len(tuning.HEADER) + 1 + tuning.INSTRUCTIONS_LIMIT)

    def test_missing_routes_change_nothing(self):
        request = self.request("research")
        self.assertIs(tuning.apply(request), request)


if __name__ == "__main__":
    unittest.main()
