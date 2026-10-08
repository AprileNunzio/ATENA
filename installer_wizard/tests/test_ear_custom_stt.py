import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

EAR = Path(__file__).resolve().parents[1] / "features" / "ear"
if str(EAR) not in sys.path:
    sys.path.append(str(EAR))

import online_stt  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class CustomSttTest(unittest.TestCase):
    def run_custom(self, env: dict):
        seen = {}

        def urlopen(request, timeout):
            seen.update(url=request.full_url, headers=dict(request.header_items()), timeout=timeout)
            return FakeResponse(b'{"text": " Atena che ore sono "}')

        base = {"ATENA_ONLINE_STT_PROVIDER": "custom", "ATENA_ONLINE_STT_KEY": ""}
        with mock.patch.dict(os.environ, {**base, **env}), mock.patch.object(online_stt.urllib.request, "urlopen", urlopen):
            text = online_stt.transcribe_online(np.zeros(1600, dtype=np.float32), "it")
        return text, seen

    def test_a_local_server_without_key_is_called_with_the_chosen_model(self):
        text, seen = self.run_custom({"ATENA_ONLINE_STT_URL": "http://192.168.1.50:8000",
                                      "ATENA_ONLINE_STT_MODEL": "google/gemma-3n-E4B-it"})
        self.assertEqual(text, "Atena che ore sono")
        self.assertEqual(seen["url"], "http://192.168.1.50:8000/v1/audio/transcriptions")
        self.assertNotIn("Authorization", seen["headers"])
        self.assertEqual(seen["timeout"], online_stt.CUSTOM_TIMEOUT)

    def test_invalid_or_missing_addresses_are_never_called(self):
        for url in ("", "ftp://server", "http://server/../../etc", "javascript:alert(1)"):
            with self.subTest(url=url):
                text, seen = self.run_custom({"ATENA_ONLINE_STT_URL": url})
                self.assertIsNone(text)
                self.assertEqual(seen, {})


if __name__ == "__main__":
    unittest.main()
