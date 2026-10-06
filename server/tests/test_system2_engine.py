import unittest
from server.core.reasoning.system2_engine import System2Engine

class TestSystem2Engine(unittest.TestCase):
    def setUp(self):
        self.engine = System2Engine()

    def test_extract_blocks(self):
        sample_output = """<thinking>
Analisi dei requisiti del cluster:
1. Tre nodi con quorum
2. Logging e snapshot
</thinking>
<response>
Ecco la configurazione del cluster proposta:
{"tool": "sysops", "arguments": {"action": "deploy_cluster"}}
</response>"""
        thinking, response, tools = self.engine.extract_blocks(sample_output)
        self.assertIn("Analisi dei requisiti del cluster", thinking)
        self.assertIn("Ecco la configurazione del cluster proposta", response)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["tool"], "sysops")

    def test_extract_blocks_fallback(self):
        sample_no_tags = "Risposta diretta senza tag."
        thinking, response, tools = self.engine.extract_blocks(sample_no_tags)
        self.assertEqual(thinking, "")
        self.assertEqual(response, "Risposta diretta senza tag.")
    def test_extract_blocks_filters_none_tool(self):
        sample_output = """<thinking>
L'utente ha salutato. Nessun tool necessario.
</thinking>
<response>
{"tool": "none", "arguments": {}}
</response>"""
        thinking, response, tools = self.engine.extract_blocks(sample_output)
        self.assertEqual(tools, [])
        self.assertNotIn("none", response)
        self.assertNotIn("{", response)

if __name__ == "__main__":
    unittest.main()
