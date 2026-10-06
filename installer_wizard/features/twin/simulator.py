import copy
from dataclasses import dataclass, field

from features.twin.model import HomeState
from features.twin.rules import BLOCK, RULES, Conflict

MAX_ROUNDS = 4


@dataclass
class Review:
    plan: dict
    conflicts: list = field(default_factory=list)
    dropped: list = field(default_factory=list)
    changes: list = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(c.severity == BLOCK for c in self.conflicts)

    @property
    def empty(self) -> bool:
        return not any(c["entity_ids"] for c in self.plan.get("calls", []))

    def to_dict(self) -> dict:
        return {"conflicts": [c.to_dict() for c in self.conflicts], "dropped": self.dropped, "changes": self.changes,
                "blocked": self.blocked, "empty": self.empty}


def simulate(state: HomeState, plan: dict, rules: list[str]) -> tuple[HomeState, list[Conflict], list]:
    twin = state.clone()
    changed: set[str] = set()
    outcome: dict[str, str | None] = {}
    conflicts: list[Conflict] = []
    changes = []
    for index, call in enumerate(plan.get("calls", [])):
        for eid, before, after in twin.apply(call["domain"], call["service"], list(call.get("entity_ids") or []), call.get("data") or {}):
            if eid in outcome and outcome[eid] != after:
                conflicts.append(Conflict("contradictory_calls", BLOCK, (eid,), params={"call": index}))
            outcome[eid] = after
            changed.add(eid)
            changes.append({"entity": eid, "before": before, "after": after})
    for name in rules:
        conflicts.extend(RULES[name](state, twin, changed))
    return twin, conflicts, changes


def _drop(plan: dict, culprits: set[str], later_only: dict[str, int]) -> tuple[dict, list]:
    fixed = copy.deepcopy(plan)
    dropped = []
    for index, call in enumerate(fixed.get("calls", [])):
        keep = []
        for eid in call.get("entity_ids") or []:
            first = later_only.get(eid)
            if eid in culprits and (first is None or index >= first):
                dropped.append({"service": f"{call['domain']}.{call['service']}", "entity": eid})
            else:
                keep.append(eid)
        call["entity_ids"] = keep
    fixed["calls"] = [c for c in fixed.get("calls", []) if c.get("entity_ids")]
    fixed["entities"] = [e for c in fixed["calls"] for e in c["entity_ids"]]
    return fixed, dropped


def review(state: HomeState, plan: dict, rules: list[str], correct: bool = True) -> Review:
    current, dropped = copy.deepcopy(plan), []
    _, conflicts, changes = simulate(state, current, rules)
    for _ in range(MAX_ROUNDS if correct else 0):
        blocking = [c for c in conflicts if c.severity == BLOCK and c.culprits]
        if not blocking:
            break
        culprits = {e for c in blocking for e in c.culprits}
        later = {c.culprits[0]: c.params["call"] for c in blocking if c.rule == "contradictory_calls"}
        current, removed = _drop(current, culprits, later)
        if not removed:
            break
        dropped.extend(removed)
        _, conflicts, changes = simulate(state, current, rules)
    return Review(current, conflicts, dropped, changes)
