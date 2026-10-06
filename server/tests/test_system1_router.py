import unittest
from server.core.orchestrator.system1_router import System1Router, System1Intent

class TestSystem1Router(unittest.TestCase):
    def setUp(self):
        self.router = System1Router()

    def test_action_direct_classification(self):
        decision = self.router.classify_sync("Accendi la luce in cucina")
        self.assertEqual(decision.intent, System1Intent.ACTION_DIRECT)
        self.assertEqual(decision.target_agent, "home_assistant")
        self.assertGreater(decision.confidence, 0.5)
        self.assertLess(decision.latency_ms, 50.0)
        self.assertIn("action_direct", decision.logits)
        self.assertIn("complex_task", decision.logits)

    def test_direct_media_action(self):
        decision = self.router.classify_sync("Metti in pausa la musica")
        self.assertEqual(decision.intent, System1Intent.ACTION_DIRECT)
        self.assertEqual(decision.target_agent, "media_player")
        self.assertLess(decision.latency_ms, 50.0)

    def test_complex_task_classification(self):
        decision = self.router.classify_sync("Progetta un'architettura distribuità con Paxos e analizza le prestazioni di rete")
        self.assertEqual(decision.intent, System1Intent.COMPLEX_TASK)
        self.assertGreater(decision.confidence, 0.5)
        self.assertLess(decision.latency_ms, 50.0)

    def test_conversation_classification(self):
        decision = self.router.classify_sync("ciao")
        self.assertEqual(decision.intent, System1Intent.CONVERSATION)
        self.assertEqual(decision.target_agent, "atena_conversation")
        self.assertGreater(decision.confidence, 0.5)

    def test_whiteboard_canvas_classification(self):
        decision = self.router.classify_sync("apri la lavagna e disegniamo un diagramma")
        self.assertEqual(decision.intent, System1Intent.WHITEBOARD_CANVAS)
        self.assertEqual(decision.target_agent, "whiteboard")
        self.assertEqual(decision.surface_action, "collaborative_canvas")

    def test_browser_action_classification(self):
        decision = self.router.classify_sync("apri il sito di github e cerca le pull request")
        self.assertEqual(decision.intent, System1Intent.BROWSER_ACTION)
        self.assertEqual(decision.target_agent, "browser_agent")
        self.assertEqual(decision.surface_action, "browser_surface")

if __name__ == "__main__":
    unittest.main()
