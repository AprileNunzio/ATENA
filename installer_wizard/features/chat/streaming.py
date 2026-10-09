import asyncio
import json
from contextvars import ContextVar

import httpx

from config import CORE_URL
from core_client import core

sink: ContextVar[asyncio.Queue | None] = ContextVar("atena_stream_sink", default=None)
PREFIX = "data: "


class StreamFailed(ValueError):
    pass


def active() -> bool:
    return sink.get() is not None


def push(event: dict) -> None:
    queue = sink.get()
    if queue is not None:
        queue.put_nowait(event)


async def core_stream(payload: dict) -> dict:
    text, model, agent = [], "", ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(240.0, connect=10.0)) as client:
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {await core._token(client)}", "Accept": "text/event-stream"}
            async with client.stream("POST", f"{CORE_URL}/api/v1/conversation/stream", json=payload, headers=headers) as resp:
                if resp.status_code == 401 and attempt == 0:
                    core.token = ""
                    continue
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith(PREFIX):
                        continue
                    event = json.loads(line[len(PREFIX):])
                    if "error" in event:
                        raise StreamFailed(str(event["error"]))
                    if event.get("t"):
                        text.append(event["t"])
                        push({"type": "token", "t": event["t"]})
                    if event.get("done"):
                        model, agent = str(event.get("model") or ""), str(event.get("agent") or "")
            break
    if not text:
        raise StreamFailed("risposta vuota")
    return {"agent_id": agent or "atena_conversation", "speech_output": "".join(text), "result_data": {"model": model}}
