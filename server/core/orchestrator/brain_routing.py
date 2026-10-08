import json
import os
from typing import Dict, List, Tuple

from server.config.env import settings

AGENT_BRAIN_ENV: Dict[str, str] = {
    "research": "ATENA_LLM_RICERCATORE_ORDER",
    "domotics": "ATENA_LLM_DOMOTICO_ORDER",
    "skill_synthesizer": "ATENA_LLM_STUDIO_ORDER",
    "tool_builder": "ATENA_LLM_STUDIO_ORDER",
    "genera_modello_3d": "ATENA_LLM_3D_ORDER",
    "parametric_designer": "ATENA_LLM_3D_ORDER",
    "agent_self_healing_coder": "ATENA_LLM_CODER_ORDER",
    "analytic_reasoner": "ATENA_LLM_DEEP_ORDER",
    "kernel_planner": "ATENA_LLM_DEEP_ORDER",
    "kernel_critic": "ATENA_LLM_DEEP_ORDER",
    # Motori Cognitivi di Base (Sistema 1, 2 e Apprendimento Attivo)
    "system1_router": "ATENA_LLM_SYS1_ORDER",
    "system2_engine": "ATENA_LLM_SYS2_ORDER",
    "babbling_engine": "ATENA_LLM_EXPLORE_ORDER",
}

_cache: Tuple[int, dict] = (-1, {})


def _routes() -> dict:
    global _cache
    try:
        stamp = os.stat(settings.BRAIN_ROUTES_PATH).st_mtime_ns
    except OSError:
        return {}
    if stamp != _cache[0]:
        try:
            with open(settings.BRAIN_ROUTES_PATH, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}
        _cache = (stamp, data if isinstance(data, dict) else {})
    return _cache[1]


def _split(raw: str) -> List[str]:
    return [m.strip() for m in (raw or "").split(",") if m.strip()]


def brain_order_for(component_id: str) -> List[str]:
    published = (_routes().get("components") or {}).get(component_id)
    if isinstance(published, list):
        return [str(ref) for ref in published if ref]
    key = AGENT_BRAIN_ENV.get(component_id)
    return _split(getattr(settings, key, "")) if key else []


def tuning_for(component_id: str) -> dict:
    tuned = (_routes().get("tuning") or {}).get(component_id)
    return tuned if isinstance(tuned, dict) else {}


def has_explicit_brain(component_id: str) -> bool:
    return component_id in (_routes().get("explicit") or [])


def keep_alive_for(model: str, default: str) -> str:
    chosen = (_routes().get("keep_alive") or {}).get(model)
    return str(chosen) if chosen else default


def preferred_brain_for(agent_id: str) -> str:
    order = brain_order_for(agent_id)
    return order[0] if order else ""
