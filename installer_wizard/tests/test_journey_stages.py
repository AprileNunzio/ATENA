import asyncio
import unittest
from unittest import mock

from features.brain import stages
from features.brain.journey import JourneyStore
from features.chat.journey_flow import ChatJourney


def tracker():
    return JourneyStore().start_journey("domanda")


class StageTest(unittest.IsolatedAsyncioTestCase):
    async def test_without_a_journey_stages_are_transparent(self):
        async with stages.stage("classifier", "Classificatore") as probe:
            probe.note("nessun tracciamento")
        async with stages.attempt("tool", "Connettore") as probe:
            probe.skip()

    async def test_nested_stages_become_children_with_real_durations(self):
        t = tracker()
        token = stages.bind(t, None)
        try:
            async with stages.stage("classifier", "Classificatore Intenti") as probe:
                async with stages.stage("reasoning", "Ragionamento"):
                    await asyncio.sleep(0.12)
                probe.note("Domini: home 0.80")
        finally:
            stages.release(token)
        classifier, reasoning = t.nodes
        self.assertEqual(reasoning["p"], classifier["i"])
        self.assertEqual((classifier["s"], reasoning["s"]), ("ok", "ok"))
        self.assertEqual(classifier["d"], "Domini: home 0.80")
        self.assertGreaterEqual(reasoning["b"] - reasoning["a"], 0.1)
        self.assertIn([classifier["i"], reasoning["i"], "flow", ""], t.edges)

    async def test_failures_are_recorded_and_never_swallowed(self):
        t = tracker()
        token = stages.bind(t, None)
        try:
            with self.assertRaises(RuntimeError):
                async with stages.stage("system2", "Generazione"):
                    raise RuntimeError("modello spento")
            with self.assertRaises(ValueError):
                async with stages.attempt("tool", "Connettore"):
                    raise ValueError("risposta rotta")
        finally:
            stages.release(token)
        self.assertEqual([n["s"] for n in t.nodes], ["fail", "fail"])
        self.assertIn("modello spento", t.nodes[0]["d"])
        self.assertIn("risposta rotta", t.nodes[1]["d"])

    async def test_quick_misses_leave_no_trace_but_slow_ones_do(self):
        t = tracker()
        token = stages.bind(t, None)
        try:
            with self.assertRaises(LookupError):
                async with stages.attempt("tool", "Connettore · musica", misses=(LookupError,)):
                    raise LookupError
            with self.assertRaises(LookupError):
                async with stages.attempt("tool", "Connettore · documenti", misses=(LookupError,)):
                    await asyncio.sleep(stages.QUIET_SECONDS + 0.05)
                    raise LookupError
            async with stages.attempt("agent", "Domotica") as probe:
                probe.skip()
        finally:
            stages.release(token)
        self.assertEqual([(n["n"], n["s"]) for n in t.nodes], [("Connettore · documenti", "skip")])
        self.assertGreaterEqual(t.nodes[0]["b"] - t.nodes[0]["a"], stages.QUIET_SECONDS)


class ChatJourneyTest(unittest.IsolatedAsyncioTestCase):
    async def test_classifier_no_longer_absorbs_the_answer_generation(self):
        with mock.patch("features.chat.journey_flow.journeys", JourneyStore()):
            flow = ChatJourney("accendi la luce", "accendi la luce", "display", "utente")
            flow.begin()
            async with stages.stage("classifier", "Classificatore Intenti"):
                pass
            async with stages.stage("system2", "Generazione della risposta"):
                await asyncio.sleep(0.15)
            flow.answered({"reply": "Fatto", "agent": "core", "intent": "conversation"})
        nodes = {n["n"]: n for n in flow.tracker.nodes}
        classifier, generation = nodes["Classificatore Intenti"], nodes["Generazione della risposta"]
        self.assertLess(classifier["b"] - classifier["a"], 0.1)
        self.assertGreaterEqual(generation["b"] - generation["a"], 0.1)
        self.assertEqual(flow.tracker.state, "done")
        self.assertIsNone(stages.current())

    async def test_a_failing_answer_closes_the_journey(self):
        with mock.patch("features.chat.journey_flow.journeys", JourneyStore()):
            flow = ChatJourney("ciao", "ciao", "display", "utente")
            flow.begin()
            flow.failed(RuntimeError("nessun cervello"))
        self.assertEqual(flow.tracker.state, "failed")
        self.assertIsNone(stages.current())


if __name__ == "__main__":
    unittest.main()
