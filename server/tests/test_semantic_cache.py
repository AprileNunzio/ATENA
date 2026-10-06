import unittest
import os
import tempfile
import asyncio
from server.core.memory.semantic_cache import SemanticCache

class TestSemanticCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_file = os.path.join(self.temp_dir, "test_cache.json")
        self.cache = SemanticCache(storage_path=self.storage_file, similarity_threshold=0.85)

    def tearDown(self):
        self.cache.clear()
        if os.path.exists(self.storage_file):
            os.remove(self.storage_file)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_exact_match_lookup(self):
        async def run_test():
            await self.cache.record_success(
                query="accendi luce",
                action_result={"agent_id": "home_assistant", "speech_output": "Luce accesa"},
                embedding=[1.0, 0.0, 0.0],
            )
            res = await self.cache.lookup("Accendi Luce!")
            self.assertTrue(res.hit)
            self.assertEqual(res.strategy, "exact")
            self.assertEqual(res.action_result["speech_output"], "Luce accesa")
            self.assertEqual(res.similarity, 1.0)
            self.assertLess(res.lookup_latency_ms, 20.0)

        asyncio.run(run_test())

    def test_semantic_similarity_lookup(self):
        async def run_test():
            await self.cache.record_success(
                query="spegni le luci in salotto",
                action_result={"agent_id": "home_assistant", "speech_output": "Luci spente"},
                embedding=[0.8, 0.6, 0.0],
            )
            res_hit = await self.cache.lookup(
                query="disattiva illuminazione sala",
                query_embedding=[0.79, 0.61, 0.0],
            )
            self.assertTrue(res_hit.hit)
            self.assertEqual(res_hit.strategy, "semantic")
            self.assertGreaterEqual(res_hit.similarity, 0.85)
            self.assertEqual(res_hit.action_result["speech_output"], "Luci spente")

            res_miss = await self.cache.lookup(
                query="qual e la capitale della francia",
                query_embedding=[0.0, 0.0, 1.0],
            )
            self.assertFalse(res_miss.hit)
            self.assertEqual(res_miss.strategy, "miss")

        asyncio.run(run_test())

    def test_stats(self):
        async def run_test():
            await self.cache.record_success(
                query="test query",
                action_result={"status": "ok"},
                embedding=[1.0, 1.0],
            )
            await self.cache.lookup("test query")
            await self.cache.lookup("non existent")
            stats = self.cache.stats()
            self.assertEqual(stats["entries_count"], 1)
            self.assertEqual(stats["total_lookups"], 2)
            self.assertEqual(stats["total_hits"], 1)
            self.assertEqual(stats["hit_rate"], 0.5)

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
