import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from server.core.orchestrator import edge_export
from server.core.orchestrator.system1_router import System1Router

ESP32 = Path(__file__).resolve().parents[2] / "client_satellite" / "microcontrollers" / "esp32"
CORPUS = [
    "accendi la luce del salotto",
    "Spegni le LUCI",
    "Atena, apri la porta d'ingresso",
    "ciao come stai?",
    "buongiorno Atena",
    "apri il sito di wikipedia sulla rivoluzione francese",
    "disegna un diagramma di flusso sulla lavagna",
    "PERCHÉ il cielo è blu? spiegami la fisica",
    "perché",
    "analizza il codice e progetta una architettura migliore per il refactoring del modulo di pagamento con strategia",
    "metti in pausa la musica",
    "volume al 30%",
    "riavvia il servizio nginx e dimmi lo stato",
    "ping 192.168.1.1",
    "«accendi» le luci… grazie",
    "c’è un intruso? controlla le telecamere",
    "",
    "   ",
    "qual è la temperatura del termostato in camera da letto stasera alle ventidue e trenta",
    "uno due tre quattro cinque sei sette otto nove dieci undici dodici tredici quattordici quindici sedici diciassette diciotto diciannove venti ventuno ventidue",
    "ÀÈÌÒÙ àèìòù accendi",
    "ok perfetto grazie, buonanotte",
    "play",
    "stop stop stop",
]


@unittest.skipUnless(shutil.which("g++"), "a host C++ compiler is required")
class EdgeParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.tmp.name) / "edge_harness"
        subprocess.run(
            ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-I", str(ESP32 / "src"),
             str(ESP32 / "src" / "edge_router.cpp"), str(ESP32 / "test" / "host_harness.cpp"), "-o", str(cls.binary)],
            check=True, capture_output=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_edge(self, lines):
        out = subprocess.run([str(self.binary)], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True)
        return [json.loads(line) for line in out.stdout.splitlines()]

    def test_edge_decisions_match_the_server_router(self):
        router = System1Router()
        for query, edge in zip(CORPUS, self.run_edge(CORPUS)):
            with self.subTest(query=query):
                server = router.classify_sync(query)
                self.assertEqual(edge["intent"], server.intent.value)
                self.assertAlmostEqual(edge["confidence"], server.confidence, places=4)
                self.assertEqual(edge["agent"], server.target_agent or "")
                self.assertEqual(edge["action"], server.direct_action or "")
                for value, key in zip(edge["logits"], ("conversation", "action_direct", "whiteboard_canvas", "browser_action", "complex_task")):
                    self.assertAlmostEqual(value, server.logits[key], places=3)

    def test_only_confident_direct_actions_stay_on_the_edge(self):
        local = dict(zip(CORPUS, (d["local"] for d in self.run_edge(CORPUS))))
        self.assertTrue(local["accendi la luce del salotto"])
        self.assertFalse(local["ciao come stai?"])
        self.assertFalse(local["apri il sito di wikipedia sulla rivoluzione francese"])

    def test_hostile_input_is_bounded(self):
        decisions = self.run_edge(["a" * 3000, "luce " * 500, "\xff\xfe accendi"])
        self.assertEqual(len(decisions), 3)
        self.assertFalse(decisions[1]["local"])


class EdgeModelFreshnessTest(unittest.TestCase):
    def test_committed_header_matches_the_router(self):
        self.assertEqual(edge_export.main(["--check"]), 0, "run: python -m server.core.orchestrator.edge_export")


if __name__ == "__main__":
    unittest.main()
