import asyncio
import json
import unittest
from unittest import mock

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from features.chat import api as chat_api
from features.chat import streaming


def events(chunks: list[str]) -> list[dict]:
    return [json.loads(c[6:]) for c in chunks if c.startswith("data: ")]


async def collect(generator) -> list[str]:
    return [chunk async for chunk in generator]


class StreamChatTests(unittest.TestCase):

    def test_tokens_then_done_with_the_full_result(self):
        async def fake_chat(text, device, lang=None, heard=None):
            for piece in ("Buon", "giorno."):
                streaming.push({"type": "token", "t": piece})
                await asyncio.sleep(0)
            return JSONResponse({"reply": "Buongiorno.", "intent": "conversation"})

        with mock.patch.object(chat_api, "assistant_chat", side_effect=fake_chat):
            out = events(asyncio.run(collect(chat_api._stream_chat("ciao", "kiosk", None, {}))))
        self.assertEqual([e["t"] for e in out if e["type"] == "token"], ["Buon", "giorno."])
        self.assertEqual(out[-1], {"type": "done", "reply": "Buongiorno.", "intent": "conversation"})
        self.assertFalse(streaming.active())

    def test_errors_become_an_error_event(self):
        async def failing(text, device, lang=None, heard=None):
            raise HTTPException(503, "Atena non è ancora operativa")

        with mock.patch.object(chat_api, "assistant_chat", side_effect=failing):
            out = events(asyncio.run(collect(chat_api._stream_chat("ciao", "kiosk", None, {}))))
        self.assertEqual(out, [{"type": "error", "status": 503, "detail": "Atena non è ancora operativa"}])


class CoreStreamTests(unittest.TestCase):

    def run_stream(self, body: str):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
        real = httpx.AsyncClient
        queue: asyncio.Queue = asyncio.Queue()

        async def scenario():
            marker = streaming.sink.set(queue)
            try:
                return await streaming.core_stream({"query": "ciao"})
            finally:
                streaming.sink.reset(marker)

        with mock.patch.object(streaming.httpx, "AsyncClient", side_effect=lambda **kw: real(transport=transport, **kw)), \
                mock.patch.object(streaming.core, "_token", return_value="tok"):
            result = asyncio.run(scenario())
        return result, [queue.get_nowait() for _ in range(queue.qsize())]

    def test_reads_server_sent_events_from_the_core(self):
        body = 'data: {"t": "Sono "}\n\ndata: {"t": "Atena."}\n\ndata: {"done": true, "model": "ollama/qwen3"}\n\n'
        result, pushed = self.run_stream(body)
        self.assertEqual(result["speech_output"], "Sono Atena.")
        self.assertEqual(result["result_data"]["model"], "ollama/qwen3")
        self.assertEqual([p["t"] for p in pushed], ["Sono ", "Atena."])

    def test_core_errors_let_the_next_brain_answer(self):
        with self.assertRaises(ValueError):
            self.run_stream('data: {"error": "nessun modello"}\n\n')
        with self.assertRaises(ValueError):
            self.run_stream('data: {"done": true}\n\n')


if __name__ == "__main__":
    unittest.main()
