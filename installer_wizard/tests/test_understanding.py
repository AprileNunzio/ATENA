import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.chat import assistant
from features.chat.dialogue import dialogue
from features.desktop.desk import desk
from features.home_assistant.nlu import matching
from features.home_assistant.nlu.text import stem
from features.understanding import claims, context, router
from features.whiteboard import board as board_module, commands, service
from features.whiteboard.board import Board

DEVICE = "prova-comprensione"


def ctx(text: str, widgets=(), last_intent: str = "", age: float = 5.0) -> context.Context:
    return context.Context(text=text, plain=context.plain(text), device=DEVICE, last_text="", last_intent=last_intent, last_age=age, widgets=set(widgets),
                           history="Utente: ciao\nAtena: buongiorno")


class BareMathTest(unittest.TestCase):
    def test_only_real_expressions_count_as_follow_ups(self):
        yes = {"e adesso 7 per 8": "7 per 8", "12 + 5": "12 + 5", "2x + 3 = 11": "2x + 3 = 11", "10 meno 3": "10 meno 3", "adesso 3 piu 4": "3 piu 4",
               "2 volte 5": "2 volte 5", "3 - 1": "3 - 1"}
        for text, body in yes.items():
            self.assertEqual(commands.bare_math(text), body, text)
        for text in ("5 minuti", "2 per favore", "ciao", "7", "sono le 10 e 30", "apri la porta", "metti 3 canzoni"):
            self.assertEqual(commands.bare_math(text), "", text)


class ClaimsTest(unittest.TestCase):
    def test_the_whiteboard_is_claimed_by_keyword_by_open_board_and_by_context(self):
        self.assertEqual(claims.whiteboard(ctx("apri la lavagna a tutto schermo")), 0.97)
        self.assertEqual(claims.whiteboard(ctx("che bella questa lavagna")), 0.8)
        self.assertEqual(claims.whiteboard(ctx("apri la porta")), 0.0)
        self.assertEqual(claims.whiteboard(ctx("calcola 5 per 5")), 0.0)
        self.assertEqual(claims.whiteboard(ctx("calcola 5 per 5", {"lavagna"})), 0.9)
        self.assertEqual(claims.whiteboard(ctx("e adesso 7 per 8", {"lavagna"})), 0.9)
        self.assertGreaterEqual(claims.whiteboard(ctx("e adesso con il 3?", {"lavagna"}, "whiteboard")), 0.85)
        self.assertEqual(claims.whiteboard(ctx("e adesso con il 3?", {"lavagna"}, "weather")), 0.0)
        self.assertEqual(claims.whiteboard(ctx("e adesso con il 3?", {"lavagna"}, "whiteboard", age=4000)), 0.0)

    def test_cameras_and_music_have_their_own_scores(self):
        self.assertEqual(claims.livecam(ctx("apri la webcam")), 0.95)
        self.assertEqual(claims.livecam(ctx("apri la lavagna")), 0.0)
        self.assertEqual(claims.livecam(ctx("a tutto schermo", {"live_cam"})), 0.75)
        self.assertGreaterEqual(claims.music(ctx("metti la canzone Luna")), 0.8)
        self.assertEqual(claims.music(ctx("metti la lavagna")), 0.0)
        self.assertEqual(claims.music(ctx("che ore sono")), 0.0)

    def test_home_is_scored_by_how_well_the_device_was_recognised(self):
        from features.home_assistant.home import brain
        plans = {"nome": {"kind": "command", "how": "nome"}, "stanza": {"kind": "command", "how": "stanza"}, "q": {"kind": "query"}, "x": {"kind": "unsupported"}}
        with mock.patch.dict(brain.catalog.entities, {"light.a": {}}), mock.patch("features.home_assistant.nlu.parser.parse") as parse:
            parse.return_value = plans["nome"]
            self.assertEqual(claims.home(ctx("accendi la luce")), 0.85)
            parse.return_value = plans["stanza"]
            self.assertEqual(claims.home(ctx("accendi la luce")), 0.7)
            parse.return_value = plans["q"]
            self.assertEqual(claims.home(ctx("la porta è aperta?")), 0.8)
            parse.return_value = plans["x"]
            self.assertEqual(claims.home(ctx("apri la lavagna")), 0.3)
            parse.return_value = None
            self.assertEqual(claims.home(ctx("che ore sono")), 0.0)
        with mock.patch.dict(brain.catalog.entities, clear=True):
            self.assertEqual(claims.home(ctx("accendi la luce")), 0.0)

    def test_a_broken_scorer_never_breaks_the_understanding(self):
        with mock.patch.dict(claims.CLAIMS, {"music": mock.Mock(side_effect=RuntimeError("guasto"))}):
            self.assertEqual(claims.score_all(ctx("ciao"))["music"], 0.0)


class HomeMatchingTest(unittest.TestCase):
    entity = {"names": [("ingress", "apr", "port")], "domain": "button"}

    def score(self, text: str) -> float:
        tokens = [stem(w) for w in text.split()]
        return matching._name_score(self.entity, tokens, set(tokens), set())

    def test_a_command_verb_alone_no_longer_matches_a_device_named_after_it(self):
        self.assertEqual(self.score("apri la lavagna a tutto schermo"), 0.0)
        self.assertEqual(self.score("apri la lavagna"), 0.0)
        self.assertGreater(self.score("apri l ingresso"), 0)
        self.assertGreater(self.score("apri la porta dell ingresso"), 0)
        self.assertGreater(self.score("ingresso apri la porta"), 100)


class RouterTest(unittest.TestCase):
    def setUp(self):
        router.RING.clear()
        self.addCleanup(router.RING.clear)

    def route(self, scores: dict, text: str = "frase", **env):
        context_ = ctx(text, widgets={"lavagna"})
        with mock.patch.object(claims, "score_all", return_value=scores), mock.patch.object(context, "build", return_value=context_):
            return asyncio.run(router.route(text, DEVICE))

    def test_the_most_convincing_function_goes_first_and_weak_ones_are_dropped(self):
        decision = self.route({"home": 0.3, "whiteboard": 0.97, "music": 0.5, "livecam": 0.0})
        self.assertEqual(decision.domains, ["whiteboard", "music"])
        self.assertFalse(decision.arbitrated)
        self.assertEqual(self.route({"home": 0.1}).order, [])

    def test_close_scores_are_settled_by_the_model_reading_sentence_and_history(self):
        seen = {}

        async def generate(prompt, **kw):
            seen["prompt"] = prompt
            return {"domain": "whiteboard", "motivo": "stava facendo calcoli alla lavagna"}
        with mock.patch("features.brain.llm.generate", generate):
            decision = self.route({"home": 0.85, "whiteboard": 0.8}, "metti 5 per 5")
        self.assertEqual(decision.domains, ["whiteboard", "home"])
        self.assertTrue(decision.arbitrated)
        self.assertIn("calcoli", decision.reason)
        for needle in ("metti 5 per 5", "buongiorno", "lavagna", "home", "somiglianza 0.85"):
            self.assertIn(needle, seen["prompt"])
        self.assertTrue(router.recent()[-1]["arbitrated"])

    def test_without_a_usable_answer_the_best_score_wins(self):
        for reply in ({"domain": "inventato"}, "testo", None):
            with mock.patch("features.brain.llm.generate", mock.AsyncMock(return_value=reply)):
                self.assertEqual(self.route({"home": 0.85, "whiteboard": 0.8}).domains, ["home", "whiteboard"])
        with mock.patch("features.brain.llm.generate", mock.AsyncMock(side_effect=RuntimeError("nessun modello"))):
            decision = self.route({"home": 0.85, "whiteboard": 0.8})
        self.assertEqual((decision.domains, decision.arbitrated), (["home", "whiteboard"], False))

    def test_clear_winners_and_switched_off_reasoning_never_call_the_model(self):
        with mock.patch("features.brain.llm.generate", mock.AsyncMock(side_effect=AssertionError("non deve essere chiamato"))):
            self.assertEqual(self.route({"home": 0.6, "whiteboard": 0.97}).domains[0], "whiteboard")
            self.assertEqual(self.route({"home": 0.9, "whiteboard": 0.3}).domains[0], "home")
            with mock.patch.object(router, "reasoning", lambda: False):
                self.assertEqual(self.route({"home": 0.85, "whiteboard": 0.8}).domains[0], "home")

    def test_the_whole_layer_can_be_switched_off(self):
        with mock.patch.object(router, "enabled", lambda: False):
            self.assertEqual(self.route({"whiteboard": 0.97}).order, [])


class FlowTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(board_module, "FILE", Path(folder.name) / "b.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.board = Board()
        for module in (service, commands):
            p = mock.patch.object(module, "board", self.board)
            p.start()
            self.addCleanup(p.stop)
        desk.scan()
        saved = dict(desk.instances)
        desk.instances.clear()
        self.addCleanup(lambda: (desk.instances.clear(), desk.instances.update(saved)))
        dialogue.turns.pop(DEVICE, None)
        self.addCleanup(lambda: dialogue.turns.pop(DEVICE, None))
        router.RING.clear()

    def handle(self, text: str) -> dict:
        from features.chat import context as request_context
        from features.home_assistant.home import brain

        async def greedy_home(said: str):
            return ("Non so fare questa operazione con Ingresso Apri la porta.", {"mode": "face"}, "casa") if "apri" in said else None

        async def core(_):
            return {"speech_output": "risposta del modello"}
        token = request_context.device.set(DEVICE)
        try:
            with mock.patch.object(brain, "handle", greedy_home):
                out = asyncio.run(assistant.handle(text, core, {"lang": "it"}))
        finally:
            request_context.device.reset(token)
        dialogue.remember(DEVICE, text, out["reply"], out["intent"])
        return out

    def test_the_case_that_failed_now_works_and_the_decision_is_recorded(self):
        out = self.handle("apri la lavagna a tutto schermo")
        self.assertEqual(out["intent"], "whiteboard")
        self.assertTrue(desk.instances["lavagna"]["fullscreen"])
        self.assertEqual(router.recent()[-1]["order"][0][0], "whiteboard")

    def test_a_conversation_flows_calculation_then_bare_follow_up_then_unrelated_request(self):
        self.handle("apri la lavagna")
        self.assertEqual(self.handle("calcola 12 per 3")["intent"], "whiteboard")
        follow = self.handle("e adesso 7 per 8")
        self.assertEqual(follow["intent"], "whiteboard")
        self.assertIn("56", follow["reply"])
        self.assertEqual(self.texts()[-1], "= 56")
        self.assertEqual(self.handle("apri la porta")["intent"], "home")

    def texts(self) -> list[str]:
        return [i["text"] for i in self.board.items if i["type"] == "text"]

    def test_nothing_changes_for_sentences_no_function_claims(self):
        out = self.handle("raccontami una barzelletta")
        self.assertNotIn(out["intent"], ("whiteboard", "livecam", "music", "home"))
        self.assertEqual(router.recent()[-1]["order"], [])


if __name__ == "__main__":
    unittest.main()
