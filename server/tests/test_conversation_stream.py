import json
import unittest
from unittest import mock

import httpx

from server.core.reasoning.conversation import ConversationEngine
from server.features.llm_gateway import streaming
from server.features.llm_gateway.contracts import SYNTHETIC_MODEL, LLMMessage, LLMRequest, LLMResponse
from server.features.llm_gateway.gateway import LLMGateway


def _request(models=("granite", "qwen")) -> LLMRequest:
    return LLMRequest(model_name="x", messages=[LLMMessage(role="user", content="ciao")], models=list(models))


async def _collect(iterator) -> list[str]:
    return [piece async for piece in iterator]


class StreamingTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.gateway = LLMGateway()

    async def test_chunks_arrive_in_order_from_the_first_working_model(self):
        async def chunks(base, payload):
            if payload["model"] == "granite":
                raise httpx.ConnectError("giù")
            for piece in ("Buon", "giorno", ", signore."):
                yield piece

        with mock.patch.object(streaming, "ollama_chunks", side_effect=chunks), \
                mock.patch.object(streaming, "apply_tuning", side_effect=lambda r: r):
            pieces = await _collect(self.gateway.stream_completion(_request()))
        self.assertEqual("".join(pieces), "Buongiorno, signore.")
        self.assertEqual(self.gateway.last_stream_model, "ollama/qwen")

    async def test_without_streaming_the_normal_completion_is_used(self):
        async def broken(base, payload):
            raise httpx.ConnectError("giù")
            yield ""

        normal = LLMResponse(content="Risposta intera.", model_used="cloud:x", tokens_consumed=3, duration_ms=1)
        with mock.patch.object(streaming, "ollama_chunks", side_effect=broken), \
                mock.patch.object(streaming, "apply_tuning", side_effect=lambda r: r), \
                mock.patch.object(self.gateway, "generate_completion", return_value=normal):
            pieces = await _collect(self.gateway.stream_completion(_request()))
        self.assertEqual(pieces, ["Risposta intera."])

    async def test_no_model_at_all_is_an_error(self):
        async def broken(base, payload):
            raise httpx.ConnectError("giù")
            yield ""

        fake = LLMResponse(content="accusa ricevuta", model_used=SYNTHETIC_MODEL, tokens_consumed=0, duration_ms=1)
        with mock.patch.object(streaming, "ollama_chunks", side_effect=broken), \
                mock.patch.object(streaming, "apply_tuning", side_effect=lambda r: r), \
                mock.patch.object(self.gateway, "generate_completion", return_value=fake):
            with self.assertRaises(streaming.StreamUnavailable):
                await _collect(self.gateway.stream_completion(_request()))

    async def test_conversation_history_is_saved_after_streaming(self):
        engine = ConversationEngine()

        async def pieces(request):
            for piece in ("Sono ", "Atena."):
                yield piece

        with mock.patch("server.core.reasoning.conversation.llm_gateway.stream_completion", side_effect=pieces):
            text = "".join(await _collect(engine.reply_stream("chi sei?", "kiosk")))
        self.assertEqual(text, "Sono Atena.")
        self.assertEqual(list(engine._history["kiosk"]), [("user", "chi sei?"), ("assistant", "Sono Atena.")])


try:
    from server.cmd import api_routes
    from server.core.orchestrator.system1_router import System1Decision, System1Intent
except ImportError:
    api_routes = None


@unittest.skipIf(api_routes is None, "rotte del core non importabili in questo ambiente")
class EndpointTests(unittest.IsolatedAsyncioTestCase):

    async def test_server_sent_events_filter_the_context(self):
        seen = {}

        async def pieces(query, device, **kwargs):
            seen.update(kwargs)
            for piece in ("Ciao", "!"):
                yield piece

        payload = api_routes.UserCommandPayload(query="ciao", context={"laws": "x", "evil": 1})
        talk = System1Decision(intent=System1Intent.CONVERSATION, confidence=0.9, latency_ms=1, logits={})
        with mock.patch.object(api_routes.system1_router, "classify", return_value=talk), \
                mock.patch("server.core.reasoning.conversation.conversation_engine.reply_stream", side_effect=pieces):
            body = "".join(await _collect(api_routes._conversation_events(payload)))
        events = [json.loads(line[6:]) for line in body.split(chr(10) * 2) if line.startswith("data: ")]
        self.assertEqual(events[:2], [{"t": "Ciao"}, {"t": "!"}])
        self.assertTrue(events[-1]["done"])
        self.assertEqual(seen["laws"], "x")
        self.assertNotIn("evil", seen)

    async def test_non_conversation_requests_keep_using_the_agents(self):
        browse = System1Decision(intent=System1Intent.BROWSER_ACTION, confidence=0.9, latency_ms=1, logits={})
        result = mock.MagicMock(speech_output="Ho cercato sul web.", agent_id="browser_agent", result_data={})
        with mock.patch.object(api_routes.system1_router, "classify", return_value=browse), \
                mock.patch.object(api_routes.orchestrator_dispatcher, "dispatch_user_command", return_value=result) as dispatch:
            body = "".join(await _collect(api_routes._conversation_events(api_routes.UserCommandPayload(query="cerca il meteo"))))
        dispatch.assert_called_once()
        self.assertIn("Ho cercato sul web.", body)
        self.assertIn("browser_agent", body)


if __name__ == "__main__":
    unittest.main()
