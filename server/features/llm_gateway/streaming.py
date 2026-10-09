import json
import logging
from typing import AsyncIterator

import httpx

from server.config.env import settings
from server.core.orchestrator.brain_routing import brain_order_for, keep_alive_for
from server.features.llm_gateway.contracts import LLMRequest
from server.features.llm_gateway.supervisor_bridge import is_remote_ref
from server.features.llm_gateway.tuning import apply as apply_tuning

logger = logging.getLogger("atena.llm_gateway.stream")


class StreamUnavailable(RuntimeError):
    pass


def chain_for(request: LLMRequest) -> list[str]:
    return [m for m in request.models if m] or brain_order_for(request.component) or [settings.ATENA_LLM_MODEL or request.model_name]


def payload_for(model: str, request: LLMRequest, chain: list[str]) -> dict:
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    if request.system_prompt:
        messages.insert(0, {"role": "system", "content": request.system_prompt})
    return {"model": model, "messages": messages, "stream": True,
            "keep_alive": keep_alive_for(model, "24h" if model == (request.pinned or chain[0]) else "5m"),
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens}}


async def ollama_chunks(base_url: str, payload: dict) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        async with client.stream("POST", f"{base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise StreamUnavailable(str(data["error"]))
                piece = (data.get("message") or {}).get("content") or ""
                if piece:
                    yield piece
                if data.get("done"):
                    return


async def stream(gateway, request: LLMRequest) -> AsyncIterator[str]:
    request = apply_tuning(request)
    chain = chain_for(request)
    errors = []
    for model in chain:
        if is_remote_ref(model):
            continue
        started = False
        try:
            async for piece in ollama_chunks(gateway._ollama_url, payload_for(model, request, chain)):
                started = True
                gateway.last_stream_model = f"ollama/{model}"
                yield piece
            if started:
                return
        except (httpx.HTTPError, ValueError, StreamUnavailable) as exc:
            if started:
                raise
            errors.append(f"{model}: {exc}")
            logger.warning("Streaming non disponibile con %s: %s", model, exc)
    response = await gateway.generate_completion(request)
    if response.is_synthetic:
        raise StreamUnavailable("; ".join(errors) or "nessun modello linguistico disponibile")
    gateway.last_stream_model = response.model_used
    yield response.content
