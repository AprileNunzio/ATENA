import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release" / "version.py"
spec = importlib.util.spec_from_file_location("atena_version", SCRIPT)
version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(version)


class VersionSyncTests(unittest.TestCase):

    def test_every_component_carries_the_version_in_the_version_file(self):
        self.assertEqual(version.mismatches(version.read_version()), [],
                         "run: python scripts/release/version.py set <VERSION>")

    def test_supervisor_reports_the_same_version(self):
        from config import VERSION
        self.assertEqual(VERSION, version.read_version())

    def test_bump_rules(self):
        self.assertEqual(version.bumped("4.1.9", "patch"), "4.1.10")
        self.assertEqual(version.bumped("4.1.9", "minor"), "4.2.0")
        self.assertEqual(version.bumped("4.1.9", "major"), "5.0.0")
        self.assertLess(version.version_code("4.1.999"), version.version_code("4.2.0"))


if __name__ == "__main__":
    unittest.main()
