# flake8: noqa: E501, E203
import re
import json
import time
import httpx
from typing import Dict, List, Optional, AsyncGenerator, Any
from pydantic import BaseModel, Field
from server.config.env import settings
from server.features.llm_gateway.gateway import llm_gateway
from server.features.llm_gateway.contracts import LLMRequest, LLMMessage

SYSTEM2_PROMPT = """Tu sei il Motore di Ragionamento Latente System 2 di Atena.
Per compiti complessi o analitici, devi seguire questa struttura formale:

<thinking>
Scrivi qui il processo di ragionamento logico analitico, la decomposizione del problema in sotto-obiettivi, la verifica dei vincoli e la strategia di risoluzione.
</thinking>
<response>
Scrivi qui la risposta finale esauriente in linguaggio naturale per l'utente. Se è richiesta un'azione con uno strumento, includi alla fine la chiamata JSON:
{"tool": "nome_strumento", "arguments": {}}
Se non serve alcuno strumento, rispondi con il testo discorsivo senza blocchi JSON.
</response>

Non aggiungere alcun testo prima di <thinking> o dopo </response>."""


class System2Chunk(BaseModel):
    chunk_type: str
    content: str
    is_complete: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class System2ExecutionResult(BaseModel):
    thinking: str
    response: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    raw_output: str
    latency_ms: float
    model_used: str


class System2Engine:
    def __init__(self, default_model: Optional[str] = None) -> None:
        self.default_model = default_model or settings.SYSTEM2_MODEL

    @staticmethod
    def _find_json_objects(text: str) -> List[Dict[str, Any]]:
        results = []
        i = 0
        n = len(text)
        while i < n:
            if text[i] == "{":
                depth = 0
                start = i
                for j in range(i, n):
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = text[start : j + 1]
                            try:
                                data = json.loads(candidate)
                                if isinstance(data, dict):
                                    results.append(data)
                            except Exception:
                                pass
                            i = j
                            break
            i += 1
        return results

    @classmethod
    def extract_blocks(cls, raw_text: str) -> tuple[str, str, List[Dict[str, Any]]]:
        thinking = ""
        response = ""
        tools: List[Dict[str, Any]] = []

        m_think = re.search(
            r"<thinking>(.*?)</thinking>", raw_text, re.DOTALL | re.IGNORECASE
        )
        if m_think:
            thinking = m_think.group(1).strip()
        else:
            if "<thinking>" in raw_text:
                parts = raw_text.split("<thinking>", 1)[1]
                if "<response>" in parts:
                    thinking = (
                        parts.split("<response>", 1)[0]
                        .replace("</thinking>", "")
                        .strip()
                    )
                else:
                    thinking = parts.strip()

        m_resp = re.search(
            r"<response>(.*?)</response>", raw_text, re.DOTALL | re.IGNORECASE
        )
        if m_resp:
            response = m_resp.group(1).strip()
        else:
            if "<response>" in raw_text:
                response = (
                    raw_text.split("<response>", 1)[1]
                    .replace("</response>", "")
                    .strip()
                )
            elif not thinking:
                response = raw_text.strip()

        parsed_objects = cls._find_json_objects(response)
        for obj in parsed_objects:
            t = str(obj.get("tool") or obj.get("action") or "").lower()
            if t and t not in ("none", "null"):
                tools.append(obj)
            if t in ("none", "null"):
                try:
                    response = response.replace(json.dumps(obj), "").strip()
                except Exception:
                    pass

        response = re.sub(r'\{\s*"tool"\s*:\s*"none"[^}]*\}', "", response).strip()
        if not response and thinking:
            response = thinking.split("\n")[0].strip()
        if not response:
            response = "Al suo servizio, signore. In cosa posso esserle utile?"

        return thinking, response, tools

    async def execute(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        model_override: Optional[str] = None,
    ) -> System2ExecutionResult:
        t0 = time.perf_counter()
        active_model = model_override or self.default_model
        messages = [LLMMessage(role="user", content=query)]

        llm_resp = await llm_gateway.generate_completion(
            LLMRequest(
                model_name=active_model,
                messages=messages,
                system_prompt=SYSTEM2_PROMPT,
                temperature=0.2,
                max_tokens=2048,
                component="system2_latent_engine",
            )
        )

        thinking, response_text, tool_calls = self.extract_blocks(llm_resp.content)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return System2ExecutionResult(
            thinking=thinking,
            response=response_text,
            tool_calls=tool_calls,
            raw_output=llm_resp.content,
            latency_ms=round(elapsed_ms, 2),
            model_used=llm_resp.model_used,
        )

    async def stream_execute(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        model_override: Optional[str] = None,
    ) -> AsyncGenerator[System2Chunk, None]:
        active_model = model_override or self.default_model
        ollama_url = settings.OLLAMA_BASE_URL
        messages = [
            {"role": "system", "content": SYSTEM2_PROMPT},
            {"role": "user", "content": query},
        ]
        payload = {
            "model": active_model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.2, "num_predict": 2048},
        }

        buffer = ""
        current_tag = None
        has_sent_thinking = False

        yield System2Chunk(
            chunk_type="status", content="System 2 Latent Reasoning activated"
        )

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream(
                    "POST", f"{ollama_url}/api/chat", json=payload
                ) as resp:
                    if resp.status_code == 200:
                        async for line in resp.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                chunk_json = json.loads(line)
                            except Exception:
                                continue
                            token = chunk_json.get("message", {}).get("content", "")
                            if not token:
                                continue
                            buffer += token

                            if "<thinking>" in buffer and current_tag != "response":
                                if current_tag is None:
                                    current_tag = "thinking"
                                    after = buffer.split("<thinking>", 1)[1]
                                    buffer = after
                                if "</thinking>" in buffer:
                                    think_part, rest = buffer.split("</thinking>", 1)
                                    if think_part:
                                        yield System2Chunk(
                                            chunk_type="thinking", content=think_part
                                        )
                                    buffer = rest
                                    current_tag = "between"
                                else:
                                    yield System2Chunk(
                                        chunk_type="thinking", content=buffer
                                    )
                                    has_sent_thinking = True
                                    buffer = ""

                            if "<response>" in buffer or current_tag == "response":
                                if current_tag != "response":
                                    current_tag = "response"
                                    after = buffer.split("<response>", 1)[1]
                                    buffer = after
                                if "</response>" in buffer:
                                    resp_part, _ = buffer.split("</response>", 1)
                                    if resp_part:
                                        yield System2Chunk(
                                            chunk_type="response", content=resp_part
                                        )
                                    buffer = ""
                                else:
                                    yield System2Chunk(
                                        chunk_type="response", content=buffer
                                    )
                                    buffer = ""

                        if buffer.strip():
                            target = (
                                "response"
                                if current_tag == "response" or has_sent_thinking
                                else "thinking"
                            )
                            clean_buf = (
                                buffer.replace("</thinking>", "")
                                .replace("</response>", "")
                                .strip()
                            )
                            if clean_buf:
                                yield System2Chunk(chunk_type=target, content=clean_buf)
                    else:
                        res = await self.execute(query, context, model_override)
                        if res.thinking:
                            yield System2Chunk(
                                chunk_type="thinking", content=res.thinking
                            )
                        if res.response:
                            yield System2Chunk(
                                chunk_type="response", content=res.response
                            )
        except Exception:
            res = await self.execute(query, context, model_override)
            if res.thinking:
                yield System2Chunk(chunk_type="thinking", content=res.thinking)
            if res.response:
                yield System2Chunk(chunk_type="response", content=res.response)

        yield System2Chunk(chunk_type="done", content="", is_complete=True)


system2_engine = System2Engine()
