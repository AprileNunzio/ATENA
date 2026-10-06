from fastapi import HTTPException

import health
from config import DEMO, _ollama_cache, write_env
from feature_registry import registry
from features.brain.brains import brains
from orchestrator import converge_steps
from state import store
from steps import STEP_BY_ID
from tasks import background

STEP_TRIGGERS = (
    ({"ATENA_LLM_MODEL", "ATENA_EMBED_MODEL", "ATENA_LLM_FAST_MODEL"}, ["preflight", "models", "warmup"]),
    ({"ATENA_LLM_MODEL", "ATENA_EMBED_MODEL"}, ["services"]),
    ({"GEMINI_API_KEY", "ANTHROPIC_API_KEY", "HOME_ASSISTANT_URL", "HOME_ASSISTANT_TOKEN"}, ["services"]),
    ({"ATENA_KIOSK"}, ["kiosk"]),
    ({"ATENA_VOICE"}, ["voice"]),
    ({"ATENA_VISION"}, ["vision"]),
    ({"ATENA_EAR", "ATENA_STT_MODEL"}, ["ear"]),
    ({"ATENA_MUSIC_ID", "ATENA_EAR"}, ["music"]),
    ({"ATENA_STUDY_FINETUNE"}, ["soup"]),
    ({"ATENA_3D_CONVERT"}, ["convert3d"]),
    ({"ATENA_COMMERCIAL", "ATENA_UNOFFICIAL_SERVICES"}, ["voice", "ear", "music", "models"]),
    ({"ATENA_GPU_DRIVER"}, ["display_driver"]),
    ({"ATENA_SHARES", "ATENA_SMB_PASSWORD"}, ["shares"]),
    ({"ATENA_OLLAMA_URL"}, ["ollama", "models", "warmup", "services"]),
)


def normalize_ollama(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    if ":" not in url.split("//", 1)[1]:
        url += ":11434"
    if any(c.isspace() for c in url) or url.count("//") != 1:
        raise HTTPException(400, "Indirizzo del server Ollama non valido")
    return url


async def apply_config(updates: dict, user: str, extra_steps: list | None = None) -> list:
    if "ATENA_OLLAMA_URL" in updates:
        updates["ATENA_OLLAMA_URL"] = normalize_ollama(updates["ATENA_OLLAMA_URL"])
    if "ATENA_LLM_MODEL" in updates:
        updates["ATENA_LLM_MODEL_AUTO"] = "0" if updates["ATENA_LLM_MODEL"] else "1"
    if "ATENA_LLM_FAST_MODEL" in updates:
        updates["ATENA_LLM_FAST_AUTO"] = "0" if updates["ATENA_LLM_FAST_MODEL"] else "1"
    try:
        write_env(updates)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    registry.note_env_change(updates)
    if "ATENA_OLLAMA_URL" in updates:
        _ollama_cache.clear()
    brains.invalidate()
    store.event("INFO", f"Configurazione aggiornata da {user}: {', '.join(updates)}", "admin")
    needs = list(extra_steps or [])
    for keys, steps in STEP_TRIGGERS:
        if keys & updates.keys():
            needs += steps
    needs = [n for n in dict.fromkeys(needs) if n in STEP_BY_ID]
    if needs:
        if "services" in needs and not DEMO:
            await health.sh("docker", "rm", "-f", "atena-core", timeout=60)
        background(converge_steps(needs, "Applicazione della nuova configurazione"))
    return needs
