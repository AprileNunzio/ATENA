from dataclasses import dataclass, field

from features.flows.domain.catalog import NODE_BY_ID, NODES, TEMPLATES, VIEW_H, VIEW_W, defaults

CUSTOM = ""
TRAITS = ("speed", "quality", "privacy", "saving")
MARGIN = 40


@dataclass(frozen=True)
class Draft:
    picks: dict = field(default_factory=dict)
    positions: dict = field(default_factory=dict)
    template: str = ""

    def as_dict(self) -> dict:
        return {"picks": dict(self.picks), "positions": {k: list(v) for k, v in self.positions.items()}, "template": self.template}


def _position(value) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not all(isinstance(v, (int, float)) for v in value):
        raise ValueError("Posizione di un nodo non valida")
    x, y = (round(float(v)) for v in value)
    if not (MARGIN <= x <= VIEW_W - MARGIN and MARGIN <= y <= VIEW_H - MARGIN):
        raise ValueError("Nodo fuori dall'area del diagramma")
    return x, y


def parse(raw, current: dict[str, str]) -> Draft:
    if not isinstance(raw, dict):
        raise ValueError("Bozza non valida")
    picks_raw, positions_raw = raw.get("picks", {}), raw.get("positions", {})
    if not isinstance(picks_raw, dict) or not isinstance(positions_raw, dict):
        raise ValueError("Bozza non valida")
    unknown = (set(picks_raw) | set(positions_raw)) - set(NODE_BY_ID)
    if unknown:
        raise ValueError(f"Nodo sconosciuto: {', '.join(sorted(unknown))}")
    picks = {}
    for node in NODES:
        choice = picks_raw.get(node.id, current.get(node.id, node.default.id))
        if choice == CUSTOM:
            picks[node.id] = current.get(node.id, node.default.id)
            continue
        algorithm = node.algorithm(choice) if isinstance(choice, str) else None
        if algorithm is None:
            raise ValueError(f"Algoritmo non valido per «{node.label}»")
        if not algorithm.available:
            raise ValueError(f"«{algorithm.name}» non è ancora disponibile")
        if node.locked and not algorithm.default:
            raise ValueError(f"Il nodo «{node.label}» è protetto")
        picks[node.id] = choice
    positions = {nid: _position(value) for nid, value in positions_raw.items()}
    template = raw.get("template", "")
    if template not in TEMPLATES and template not in ("", "custom"):
        raise ValueError("Modello di flusso sconosciuto")
    return Draft(picks, positions, template)


def effects(picks: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in NODES:
        algorithm = node.algorithm(picks.get(node.id, ""))
        if algorithm:
            out.update(algorithm.effects)
    return out


def infer(settings: dict[str, str]) -> dict[str, str]:
    picks = {}
    for node in NODES:
        controlled = [a for a in node.algorithms if a.effects]
        if not controlled:
            picks[node.id] = node.default.id
            continue
        match = next((a for a in controlled if all(settings.get(k) == v for k, v in a.effects.items())), None)
        picks[node.id] = match.id if match else CUSTOM
    return picks


def changes(picks: dict[str, str], settings: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in effects(picks).items() if settings.get(k) != v}


def traits(picks: dict[str, str]) -> dict[str, float]:
    chosen = [NODE_BY_ID[nid].algorithm(aid) for nid, aid in picks.items() if NODE_BY_ID[nid].editable]
    chosen = [a for a in chosen if a]
    if not chosen:
        return {t: 0.0 for t in TRAITS}
    return {t: round(sum(a.traits[t] for a in chosen) / len(chosen), 2) for t in TRAITS}


def estimate(picks: dict[str, str]) -> list[dict]:
    steps = []
    for node in NODES:
        algorithm = node.algorithm(picks.get(node.id, "")) or node.default
        seconds = node.base_seconds * (1 + (5 - algorithm.speed) * 0.45)
        steps.append({"node": node.id, "algorithm": algorithm.id, "seconds": round(seconds, 2)})
    return steps


def initial(current: dict[str, str]) -> Draft:
    return Draft({**defaults(), **current}, {}, "")
