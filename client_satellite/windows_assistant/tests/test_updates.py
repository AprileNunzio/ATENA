import base64
import hashlib
import json
import unittest
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from updates import manifest, updater

INSTALLER = b"MZ" + b"\x00" * 1000
URL = "https://github.com/AprileNunzio/ATENA/releases/download/assistant-v1.2.0/ATENA_Assistente_Setup.exe"


def keypair():
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, base64.b64encode(public).decode()


def signed(key, **overrides):
    body = {"version": "1.2.0", "url": URL, "sha256": hashlib.sha256(INSTALLER).hexdigest(), "size": len(INSTALLER)}
    data = json.dumps({**body, **overrides}).encode()
    return data, base64.b64encode(key.sign(data))


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.key, self.public = keypair()

    def test_a_properly_signed_release_is_accepted_and_checked(self):
        data, signature = signed(self.key)
        release = manifest.verify(data, signature, self.public)
        self.assertEqual(release.version, "1.2.0")
        manifest.check_file(INSTALLER, release)
        with self.assertRaises(manifest.UpdateRejected):
            manifest.check_file(INSTALLER + b"x", release)
        with self.assertRaises(manifest.UpdateRejected):
            manifest.check_file(b"MZ" + b"\x01" * 1000, release)

    def test_tampered_or_foreign_signatures_are_rejected(self):
        data, signature = signed(self.key)
        with self.assertRaises(manifest.UpdateRejected):
            manifest.verify(data.replace(b"1.2.0", b"9.9.9"), signature, self.public)
        other, _public = keypair()
        foreign_data, foreign_signature = signed(other)
        with self.assertRaises(manifest.UpdateRejected):
            manifest.verify(foreign_data, foreign_signature, self.public)
        with self.assertRaises(manifest.UpdateRejected):
            manifest.verify(data, b"non-base64!!", self.public)

    def test_only_official_download_addresses(self):
        for url in ("https://evil.example/ATENA_Assistente_Setup.exe",
                    "https://github.com/someone/ATENA/releases/download/assistant-v1.2.0/x.exe",
                    "http://github.com/AprileNunzio/ATENA/releases/download/assistant-v1.2.0/x.exe"):
            data, signature = signed(self.key, url=url)
            with self.subTest(url=url), self.assertRaises(manifest.UpdateRejected):
                manifest.verify(data, signature, self.public)

    def test_versions(self):
        self.assertTrue(manifest.newer("1.10.0", "1.9.3"))
        self.assertFalse(manifest.newer("1.1.0", "1.1.0"))
        with self.assertRaises(manifest.UpdateRejected):
            manifest.newer("1.x", "1.0")

    def test_embedded_public_key_is_a_valid_ed25519_key(self):
        self.assertEqual(len(base64.b64decode(manifest.PUBLIC_KEY)), 32)


class LatestTest(unittest.TestCase):
    def test_the_highest_complete_assistant_release_is_chosen(self):
        def asset(name):
            return {"name": name, "browser_download_url": f"https://x/{name}"}

        releases = [
            {"tag_name": "assistant-v1.2.0", "assets": [asset("manifest.json"), asset("manifest.sig")]},
            {"tag_name": "assistant-v1.10.0", "assets": [asset("manifest.json"), asset("manifest.sig")]},
            {"tag_name": "assistant-v2.0.0", "assets": [asset("manifest.json")]},
            {"tag_name": "assistant-v3.0.0", "draft": True, "assets": [asset("manifest.json"), asset("manifest.sig")]},
            {"tag_name": "v4.0.0", "assets": [asset("manifest.json"), asset("manifest.sig")]},
        ]
        with mock.patch.object(updater, "_get", return_value=json.dumps(releases).encode()):
            version, assets = updater.latest()
        self.assertEqual(version, "1.10.0")
        self.assertIn("manifest.sig", assets)


if __name__ == "__main__":
    unittest.main()
