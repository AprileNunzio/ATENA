import time

from state import store

from features.laws import guard

LOCAL_INTENT = "action_direct"
MIN_CONFIDENCE = 0.85
MAX_TEXT = 400


def edge_claim(body: dict) -> dict:
    edge = body.get("edge") if isinstance(body.get("edge"), dict) else {}
    try:
        confidence = float(edge.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {"intent": str(edge.get("intent") or "")[:32], "confidence": max(0.0, min(1.0, confidence)),
            "model": str(edge.get("model") or "")[:64]}


def trusted_shortcut(text: str, claim: dict) -> bool:
    return (claim["intent"] == LOCAL_INTENT and claim["confidence"] >= MIN_CONFIDENCE and 0 < len(text) <= MAX_TEXT
            and not guard.attempt(text))


async def fast_path(text: str, claim: dict) -> dict | None:
    if not trusted_shortcut(text, claim) or store.phase not in ("READY", "DEGRADED"):
        return None
    started = time.time()
    try:
        from features.home_assistant.home import brain as home_brain
        out = await home_brain.handle(text)
    except Exception as exc:
        store.event("WARN", f"Percorso rapido del satellite non disponibile: {exc}", "nodes")
        return None
    if not out:
        return None
    speech, ui, agent = out
    return {"reply": speech, "ui": ui, "intent": "home", "agent": agent, "edge": True,
            "elapsed_ms": int((time.time() - started) * 1000)}
