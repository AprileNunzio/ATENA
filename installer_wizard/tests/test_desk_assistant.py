import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.nodes import desk_assistant, trust


class CleanTest(unittest.TestCase):
    def test_new_actions_keep_only_known_fields(self):
        raw = {"reply": "Ecco", "actions": [
            {"type": "run_powershell", "command": "Get-Process", "evil": "x"},
            {"type": "ssh", "host": "nas", "user": "admin", "port": 2222, "command": "uptime"},
            {"type": "ssh", "host": "nas", "user": "admin", "port": 99999, "command": "uptime"},
            {"type": "press_keys", "keys": "ctrl+s"},
            {"type": "window", "op": "minimize", "title": "Word"},
            {"type": "format_disk", "path": "C:"}]}
        out = desk_assistant._clean(raw)
        types = [a["type"] for a in out["actions"]]
        self.assertEqual(types, ["run_powershell", "ssh", "ssh", "press_keys", "window"])
        self.assertNotIn("evil", out["actions"][0])
        self.assertEqual(out["actions"][1]["port"], 2222)
        self.assertNotIn("port", out["actions"][2])
        self.assertTrue(out["followup"])

    def test_permissions_reach_the_model_and_forbidden_ones_are_marked(self):
        body = {"env": {"permissions": {"shell.powershell": "deny", "files.create": "allow", "remote.ssh": "ask"}},
                "context": {}}
        prompt = desk_assistant._prompt("crea un file", body, [])
        self.assertIn("shell.powershell=VIETATO", prompt)
        self.assertIn("files.create=consentito", prompt)
        self.assertIn("remote.ssh=chiedi conferma", prompt)


class TrustTest(unittest.TestCase):
    def test_fingerprint_of_the_local_authority(self):
        pem = ("-----BEGIN CERTIFICATE-----\nMAA=\n-----END CERTIFICATE-----\n")
        with tempfile.TemporaryDirectory() as tmp:
            ca = Path(tmp) / "ca.pem"
            with mock.patch.object(trust, "CA_FILE", ca):
                self.assertEqual(trust.ca_fingerprint(), "")
                ca.write_text(pem, encoding="ascii")
                value = trust.ca_fingerprint()
        self.assertRegex(value, r"^[0-9A-F]{4}(-[0-9A-F]{4}){3}$")


if __name__ == "__main__":
    unittest.main()
