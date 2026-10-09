import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from features.mind import memory as memory_module


class LongTermMemoryTests(unittest.TestCase):

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for name, value in (("MIND_DIR", root), ("FACTS_FILE", root / "facts.json")):
            patcher = mock.patch.object(memory_module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.memory = memory_module.LongTermMemory()

    def test_someone_else_never_receives_personal_memories(self):
        self.memory.add("Nunzio è allergico alle arachidi", who="nunzio")
        self.memory.add("La casa ha il riscaldamento a pavimento allergico", who="")
        self.assertEqual([f["who"] for f in self.memory.recall("allergico", who="")], [""])
        self.assertEqual([f["who"] for f in self.memory.recall("allergico", who="anna")], [""])
        self.assertIn("nunzio", [f["who"] for f in self.memory.recall("allergico", who="nunzio")])

    def test_concurrent_writes_are_not_lost(self):
        def write(n):
            for i in range(10):
                self.memory.add(f"ricordo numero {n} variante {i} con testo unico {n * 100 + i}", who="nunzio")

        threads = [threading.Thread(target=write, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        reloaded = memory_module.LongTermMemory()
        self.assertEqual(len(reloaded.facts), len(self.memory.facts))
        self.assertGreater(len(reloaded.facts), 0)


if __name__ == "__main__":
    unittest.main()
