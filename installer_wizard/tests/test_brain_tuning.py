import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.brain import assignments, llm
from features.brain.routing import AssignmentService
from features.brain.trace import Trace
from features.brain.tuning import Tuning, TuningError, parse


class TuningParseTest(unittest.TestCase):
    def test_values_are_validated_and_cleaned(self):
        tuned = parse({"temperature": "0.7", "max_tokens": 1024, "timeout": 30, "instructions": "  Cita le fonti\x00  "})
        self.assertEqual((tuned.temperature, tuned.max_tokens, tuned.timeout, tuned.instructions), (0.7, 1024, 30, "Cita le fonti"))
        self.assertTrue(parse({}).empty)
        self.assertTrue(parse({"temperature": "", "max_tokens": None}).empty)
        for bad in ({"temperature": 3}, {"max_tokens": 10}, {"timeout": 9999}, {"temperature": "alta"},
                    {"instructions": "x" * 1201}):
            with self.subTest(bad=bad), self.assertRaises(TuningError):
                parse(bad)

    def test_instructions_are_appended_to_the_system_prompt(self):
        self.assertEqual(Tuning(instructions="Sii breve").system("Base"),
                         "Base\n\nIstruzioni specifiche per questo agente:\nSii breve")
        self.assertEqual(Tuning().system("Base"), "Base")


class AssignmentTuningTest(unittest.TestCase):
    def test_tuning_alone_is_a_real_assignment_and_survives_a_round_trip(self):
        parsed = assignments.parse_assignment({"tuning": {"temperature": 0.2, "instructions": "Rispondi in JSON"}})
        self.assertFalse(parsed.empty)
        again = assignments.load(assignments.dump({"research": parsed}))
        self.assertEqual(again["research"].tuning, parsed.tuning)
        with self.assertRaises(assignments.AssignmentError):
            assignments.parse_assignment({"tuning": {"temperature": 9}})

    def test_tuning_is_published_for_the_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = AssignmentService(Path(tmp))
            service.save({"research": assignments.parse_assignment({"tuning": {"max_tokens": 900}})})
            routes = json.loads((Path(tmp) / "routes.json").read_text(encoding="utf-8"))
            self.assertEqual(routes["tuning"]["research"]["max_tokens"], 900)
            self.assertEqual(service.tuning("research").max_tokens, 900)
            self.assertTrue(service.tuning("domotics").empty)


class GenerateTuningTest(unittest.TestCase):
    def test_the_agent_parameters_reach_the_model_call(self):
        calls = []

        async def fake_ollama(model, prompt, system, as_json, max_tokens, temperature, timeout):
            calls.append({"system": system, "max_tokens": max_tokens, "temperature": temperature, "timeout": timeout})
            return "risposta"

        tuned = Tuning(temperature=0.9, max_tokens=777, timeout=15, instructions="Usa un tono formale")
        with mock.patch("features.brain.routing.assignment_service.tuning", return_value=tuned), \
                mock.patch.object(llm, "component_chain", new=mock.AsyncMock(return_value=["modello-a"])), \
                mock.patch.object(llm, "chain", new=mock.AsyncMock(return_value=[])), \
                mock.patch.object(llm, "is_cloud", return_value=False), \
                mock.patch.object(llm, "_ollama", side_effect=fake_ollama), \
                mock.patch.object(llm, "background"), mock.patch.object(llm, "touch"):
            asyncio.run(llm.generate("ciao", component="research", govern=False, system="Base"))
        self.assertEqual(calls[0]["max_tokens"], 777)
        self.assertEqual(calls[0]["temperature"], 0.9)
        self.assertEqual(calls[0]["timeout"], 15)
        self.assertIn("Usa un tono formale", calls[0]["system"])


class TraceStatsTest(unittest.TestCase):
    def test_every_agent_gets_its_own_metrics(self):
        trace = Trace()
        with mock.patch("features.brain.trace.brains.describe", side_effect=lambda ref: {"label": ref}):
            ok = trace.begin("research", "", ["m1"])
            trace.attempt(ok, "m1")
            trace.finish(ok, "m1", 1200)
            bad = trace.begin("research", "", ["m1"])
            trace.abort(bad, "nessun modello")
        stats = trace.summary()["research"]
        self.assertEqual((stats["calls"], stats["success"], stats["last_model"]), (2, 50, "m1"))
        self.assertEqual(stats["last_error"], "nessun modello")


if __name__ == "__main__":
    unittest.main()
