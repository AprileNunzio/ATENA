import unittest
from unittest import mock

from features.ear import keycheck


class Response:
    def __init__(self, status):
        self.status_code = status


class KeyCheckTest(unittest.IsolatedAsyncioTestCase):
    def test_requests_per_provider(self):
        url, headers, params = keycheck._request("deepgram", "abcdefgh123", "")
        self.assertEqual((url, headers["Authorization"]), ("https://api.deepgram.com/v1/projects", "Token abcdefgh123"))
        self.assertEqual(keycheck._request("gemini", "abcdefgh123", "")[2], {"key": "abcdefgh123"})
        self.assertEqual(keycheck._request("custom", "", "http://192.168.1.5:8000/v1/audio/transcriptions")[0],
                         "http://192.168.1.5:8000/v1/models")

    def test_rejects_bad_input(self):
        for args in (("nope", "abcdefgh1", ""), ("groq", "", ""), ("groq", "bad key with spaces", ""),
                     ("custom", "", "file:///etc/passwd"), ("custom", "", "http://x/../y")):
            with self.assertRaises(keycheck.KeyCheckError):
                keycheck._request(*args)

    async def test_verdicts(self):
        for status, ok in ((200, True), (401, False), (500, False)):
            client = mock.AsyncMock()
            client.__aenter__.return_value.get = mock.AsyncMock(return_value=Response(status))
            with mock.patch.object(keycheck.httpx, "AsyncClient", return_value=client):
                self.assertEqual((await keycheck.check("openai", "abcdefgh123"))["ok"], ok)


if __name__ == "__main__":
    unittest.main()
