import time
from collections import deque
from dataclasses import dataclass, field

from config import env_get
from features.understanding import claims, context
from state import store

MIN = 0.4
CLOSE = 0.25
SURE = 0.9
RING: deque = deque(maxlen=60)
ARBITER = ("Sei il comprensore di Atena. Devi capire quale funzione vuole davvero l'utente, leggendo TUTTA la frase, il contesto e la conversazione "
           "precedente. Scegli UNA sola funzione tra quelle proposte. Rispondi SOLO con JSON: "
           '{{"domain": "nome", "motivo": "una frase"}}.\nFunzioni possibili:\n{options}\nWidget aperti ora: {widgets}\n'
           "Conversazione recente:\n{history}\n\nFrase da capire: «{text}»")


@dataclass
class Decision:
    order: list[tuple[str, float]] = field(default_factory=list)
    arbitrated: bool = False
    reason: str = ""

    @property
    def domains(self) -> list[str]:
        return [d for d, _ in self.order]


def enabled() -> bool:
    return env_get("ATENA_UNDERSTANDING", "1") != "0"


def reasoning() -> bool:
    return env_get("ATENA_UNDERSTANDING_LLM", "1") != "0"


def ambiguous(ranked: list[tuple[str, float]]) -> bool:
    return len(ranked) >= 2 and ranked[0][1] < SURE + 0.05 and ranked[0][1] - ranked[1][1] < CLOSE


async def arbitrate(ctx: context.Context, ranked: list[tuple[str, float]]) -> tuple[str, str] | None:
    from features.brain.llm import generate
    names = [d for d, _ in ranked]
    options = "\n".join(f"- {d}: {claims.DESCRIPTIONS.get(d, d)} (somiglianza {s:.2f})" for d, s in ranked)
    prompt = ARBITER.format(options=options, widgets=", ".join(sorted(ctx.widgets)) or "nessuno", history=ctx.history or "nessuna", text=ctx.text[:400])
    try:
        reply = await generate(prompt, as_json=True, max_tokens=120, temperature=0.0, kind="chat", timeout=8)
    except Exception:
        return None
    if isinstance(reply, dict) and reply.get("domain") in names:
        return reply["domain"], str(reply.get("motivo", ""))[:160]
    return None


def note(ctx: context.Context, decision: Decision) -> None:
    RING.append({"at": time.time(), "text": ctx.text[:160], "order": decision.order, "arbitrated": decision.arbitrated, "reason": decision.reason,
                 "last_intent": ctx.last_intent})
    if decision.order:
        top = decision.order[0]
        store.event("INFO", f"Comprensione «{ctx.text[:80]}» → {top[0]} ({top[1]:.2f})" + (f", scelto ragionando: {decision.reason}" if decision.arbitrated else ""), "understanding")


async def route(text: str, device: str) -> Decision:
    if not enabled():
        return Decision()
    ctx = context.build(text, device)
    ranked = sorted(((d, s) for d, s in claims.score_all(ctx).items() if s >= MIN), key=lambda x: -x[1])
    decision = Decision(order=ranked)
    if ambiguous(ranked) and reasoning():
        chosen = await arbitrate(ctx, ranked)
        if chosen:
            first = next(x for x in ranked if x[0] == chosen[0])
            decision = Decision(order=[first] + [x for x in ranked if x[0] != chosen[0]], arbitrated=True, reason=chosen[1])
    note(ctx, decision)
    return decision


def recent(limit: int = 40) -> list[dict]:
    return list(RING)[-limit:]
