from typing import Callable

from features.nexus.domain import summary
from features.nexus.domain.zones import FAMILIES, ZONES, classify


class SummaryService:
    def __init__(self, state: Callable[[], dict], catalog: Callable[[], dict], step_titles: Callable[[], dict],
                 approvals: Callable[[], int]) -> None:
        self.state = state
        self.catalog = catalog
        self.step_titles = step_titles
        self.approvals = approvals

    @staticmethod
    def _tool(item: dict) -> dict:
        state = item.get("state") or {}
        return {"id": item["id"], "name": item.get("name", item["id"]), "icon": item.get("icon", "◆"),
                "description": item.get("description", ""), "panel": item.get("panel", ""),
                "enabled": bool(state.get("enabled")), "mode": state.get("mode", "1"), "reason": state.get("reason", ""),
                "fixed": bool(state.get("fixed")), "risk": bool(state.get("risk")), "pinned": bool(item.get("pinned")),
                "toggle": bool(item.get("toggle")), **classify(item).as_dict()}

    def build(self) -> dict:
        snap = self.state()
        features = self.catalog().get("features", [])
        tools = [self._tool(f) for f in features]
        inputs = summary.Inputs(phase=snap.get("phase", ""), progress=float(snap.get("progress") or 0),
                                steps=snap.get("steps") or {}, step_titles=self.step_titles(),
                                components=snap.get("components") or {}, features=features,
                                update=snap.get("update") or {}, approvals=self.approvals())
        active = sum(1 for t in tools if t["enabled"])
        return {
            "phase": inputs.phase,
            "tone": summary.tone(inputs),
            "health": summary.health(inputs.components),
            "headline": summary.headline(inputs, active, len(tools)),
            "todos": [t.as_dict() for t in summary.todos(inputs)],
            "counts": {"total": len(tools), "active": active,
                       "zones": {z: sum(1 for t in tools if t["zone"] == z) for z in ZONES}},
            "families": FAMILIES,
            "tools": tools,
            "components": [{"id": k, "label": v.get("label", k), "status": v.get("status", ""), "detail": v.get("detail", ""),
                            "on_demand": bool(v.get("on_demand"))} for k, v in inputs.components.items()],
        }
