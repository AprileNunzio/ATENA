from server.core.orchestrator.brain_routing import tuning_for
from server.features.llm_gateway.contracts import LLMRequest

TEMPERATURE = (0.0, 1.5)
MAX_TOKENS = (64, 16384)
INSTRUCTIONS_LIMIT = 1200
HEADER = "Istruzioni specifiche per questo agente:"


def _bounded(value, bounds: tuple, kind):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return kind(min(max(value, bounds[0]), bounds[1]))


def apply(request: LLMRequest) -> LLMRequest:
    tuned = tuning_for(request.component) if request.component else {}
    if not tuned:
        return request
    update = {}
    temperature = _bounded(tuned.get("temperature"), TEMPERATURE, float)
    if temperature is not None:
        update["temperature"] = temperature
    max_tokens = _bounded(tuned.get("max_tokens"), MAX_TOKENS, int)
    if max_tokens is not None:
        update["max_tokens"] = max_tokens
    instructions = str(tuned.get("instructions") or "").strip()[:INSTRUCTIONS_LIMIT]
    if instructions:
        extra = "\n".join((HEADER, instructions))
        update["system_prompt"] = "\n\n".join(p for p in (request.system_prompt or "", extra) if p)
    return request.model_copy(update=update)
