from features.home_assistant.automations import describe, model
from features.home_assistant.automations.model import AutomationError

MAX_ENTITIES = 220
_USEFUL = ("light", "switch", "cover", "climate", "media_player", "lock", "fan", "scene", "script", "vacuum",
           "binary_sensor", "sensor", "person", "device_tracker", "alarm_control_panel", "input_boolean", "button")
_EXAMPLE = ('{"alias": "Luce ingresso di notte", "description": "...", "mode": "single", '
            '"triggers": [{"trigger": "state", "entity_id": "binary_sensor.porta", "to": "on"}], '
            '"conditions": [{"condition": "sun", "after": "sunset", "before": "sunrise"}], '
            '"actions": [{"action": "light.turn_on", "target": {"entity_id": "light.ingresso"}}]}')


def _catalog(brain) -> list[str]:
    rows = []
    for e in brain.entities.values():
        if e["domain"] not in _USEFUL or e.get("disabled") or e.get("hidden") or e.get("category"):
            continue
        area = brain.areas.get(e.get("area_id") or "", {}).get("name", "-")
        state = (brain.states.get(e["entity_id"]) or {}).get("state", "")
        rows.append(f"{e['entity_id']} | {e['name']} | {area} | {state}")
    return rows[:MAX_ENTITIES]


async def draft(brain, request: str, name) -> dict:
    request = request.strip()[:600]
    if len(request) < 6:
        raise AutomationError("Descrivi l'automazione con qualche parola in più")
    entities = _catalog(brain)
    if not entities:
        raise AutomationError("Nessun dispositivo di Home Assistant disponibile")
    prompt = (
        "Sei l'esperto di Home Assistant di Atena. Scrivi UNA automazione Home Assistant (formato 2024.10+, chiavi "
        "triggers/conditions/actions, \"trigger\" al posto di \"platform\", \"action\" al posto di \"service\") che "
        "realizzi la richiesta. Usa SOLO le entità elencate. Rispondi solo con JSON, come questo esempio:\n"
        f"{_EXAMPLE}\n\nEntità (id | nome | stanza | stato):\n" + "\n".join(entities)
        + f"\n\nRichiesta: {request}\nJSON:")
    from features.brain.llm import BrainUnavailable, generate
    try:
        spec = await generate(prompt, as_json=True, max_tokens=900, temperature=0.1, kind="deep", timeout=120)
    except (BrainUnavailable, ValueError) as exc:
        raise AutomationError(f"Il cervello non è riuscito a progettarla: {str(exc)[:160]}") from exc
    config = model.normalize(spec if isinstance(spec, dict) else {})
    unknown = sorted(e for e in model.entity_ids(config)
                     if "{{" not in e and e not in brain.entities and e not in brain.states)
    return {"config": config, "summary": describe.summary(config, name), "unknown_entities": unknown}
