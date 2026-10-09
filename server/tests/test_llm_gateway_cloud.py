import unittest
from unittest import mock

from server.config.env import settings
from server.core.reasoning.conversation import ConversationEngine
from server.features.llm_gateway import gateway as gateway_module
from server.features.llm_gateway.contracts import SYNTHETIC_MODEL, LLMMessage, LLMRequest, LLMResponse
from server.shared.errors.domain_errors import AgentExecutionException


class FakeResponse:
    def __init__(self, data: dict) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


class FakeClient:
    calls: list = []

    def __init__(self, *args, **kwargs) -> None:
        self.reply = kwargs.pop("_reply", None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        FakeClient.calls.append({"url": url, "json": json, "headers": headers or {}})
        if "anthropic" in url:
            return FakeResponse({"model": json["model"], "content": [{"type": "text", "text": "Buongiorno."}],
                                 "usage": {"output_tokens": 3}})
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "ok"}]}}], "usageMetadata": {}})


def _request() -> LLMRequest:
    return LLMRequest(model_name="x", messages=[LLMMessage(role="user", content="ciao")], system_prompt="Sei Atena.")


class CloudProviderTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        FakeClient.calls = []
        patcher = mock.patch.object(gateway_module.httpx, "AsyncClient", FakeClient)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.gateway = gateway_module.LLMGateway()

    async def test_claude_uses_the_configured_model_and_prompt_caching(self):
        self.gateway._claude_api_key = "test-key"
        reply = await self.gateway._call_claude(_request(), 0.0)
        payload = FakeClient.calls[0]["json"]
        self.assertEqual(payload["model"], settings.ATENA_CLAUDE_MODEL)
        self.assertNotIn("claude-3", payload["model"])
        self.assertEqual(payload["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual((reply.content, reply.model_used), ("Buongiorno.", settings.ATENA_CLAUDE_MODEL))

    async def test_gemini_key_travels_in_a_header_not_in_the_url(self):
        self.gateway._gemini_api_key = "secret-key"
        await self.gateway._call_gemini(_request(), 0.0)
        call = FakeClient.calls[0]
        self.assertNotIn("secret-key", call["url"])
        self.assertEqual(call["headers"]["x-goog-api-key"], "secret-key")


class ConversationFailureTests(unittest.IsolatedAsyncioTestCase):

    async def test_no_model_is_an_error_not_a_fake_answer(self):
        engine = ConversationEngine()
        fake = LLMResponse(content="Atena Core accusa ricevuta", model_used=SYNTHETIC_MODEL, tokens_consumed=0, duration_ms=1)
        with mock.patch("server.core.reasoning.conversation.llm_gateway.generate_completion", return_value=fake):
            with self.assertRaises(AgentExecutionException):
                await engine.reply("che tempo fa?", "kiosk")
        self.assertEqual(list(engine._history["kiosk"]), [])


if __name__ == "__main__":
    unittest.main()
