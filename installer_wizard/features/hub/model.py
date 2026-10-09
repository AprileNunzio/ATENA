from features.brain.components import BY_ID as COMPONENTS

STATIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("input", "Ingresso", ("input",)),
    ("laws", "Leggi", ("laws",)),
    ("memory", "Memoria rapida", ("cache",)),
    ("router", "Smistamento", ("router", "classifier", "flow", "call", "fallback")),
    ("plan", "Pianificazione", ("planner", "decision", "dag_node")),
    ("agents", "Agenti", ("pool", "agent", "reasoning", "system2", "skill", "attempt")),
    ("tools", "Strumenti", ("tool",)),
    ("check", "Giudizio", ("jury", "voter")),
    ("answer", "Risposta", ("answer", "error")),
)
STATION_OF = {kind: index for index, (_, _, kinds) in enumerate(STATIONS) for kind in kinds}
DESKS = ("conversation", "agent", "home_commands", "mind", "presentation", "documents", "research", "domotics",
         "analytic_reasoner", "kernel_planner", "kernel_critic", "firewall")
MAX_JOURNEYS = 3


def station(kind: str) -> int:
    return STATION_OF.get(kind, 3)


def journey_view(j: dict) -> dict:
    nodes = j.get("nodes") or []
    reached = max((station(n.get("k", "")) for n in nodes), default=0)
    failed = any(n.get("k") == "error" or (n.get("s") == "fail" and n.get("k") == "answer") for n in nodes)
    steps = [{"station": station(n.get("k", "")), "name": n.get("n", ""), "state": n.get("s", "")} for n in nodes[-40:]]
    return {"id": j.get("id"), "query": str(j.get("query") or "")[:140], "who": j.get("who", ""), "state": j.get("state", ""),
            "reached": reached, "failed": failed, "agent": j.get("agent", ""), "answer": str(j.get("answer") or "")[:200],
            "started": j.get("started"), "steps": steps}


def desk_view(component_id: str, active: list[dict], summary: dict) -> dict:
    known = COMPONENTS.get(component_id)
    call = next((a for a in active if a.get("component") == component_id), None)
    stats = summary.get(component_id) or {}
    return {"id": component_id, "label": known.label if known else component_id, "group": known.group if known else "",
            "role": known.role if known else "", "busy": bool(call),
            "model": ((call or {}).get("model") or {}).get("model", "") if call else stats.get("last_model", "") or "",
            "doing": (call or {}).get("steps", [{}])[-1].get("text", "") if call else "",
            "calls": stats.get("calls", 0), "avg_ms": stats.get("avg_ms", 0)}


def stations() -> list[dict]:
    return [{"id": sid, "label": label} for sid, label, _ in STATIONS]
