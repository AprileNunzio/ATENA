from typing import Callable

from features.nexus.domain import summary
from features.nexus.domain.zones import FAMILIES, ZONES, classify


class SummaryService:
    def __init__(self, state: Callable[[], dict], catalog: Callable[[], dict], step_titles: Callable[[], dict],
                 approvals: Callable[[], int], badges: Callable[[], dict] = dict,
                 awakening: Callable[[], dict] = dict) -> None:
        self.state = state
        self.catalog = catalog
        self.step_titles = step_titles
        self.approvals = approvals
        self.badges = badges
        self.awakening = awakening

    @staticmethod
    def _tool(item: dict, fresh: dict) -> dict:
        state = item.get("state") or {}
        return {"id": item["id"], "name": item.get("name", item["id"]), "icon": item.get("icon", "◆"),
                "description": item.get("description", ""), "panel": item.get("panel", ""),
                "enabled": bool(state.get("enabled")), "mode": state.get("mode", "1"), "reason": state.get("reason", ""),
                "fixed": bool(state.get("fixed")), "risk": bool(state.get("risk")), "pinned": bool(item.get("pinned")),
                "toggle": bool(item.get("toggle")), **classify(item).as_dict(),
                **fresh.get(item["id"], {"badge": "", "since": 0})}

    def build(self) -> dict:
        snap = self.state()
        features = self.catalog().get("features", [])
        fresh = self.badges()
        journey = self.awakening()
        tools = [self._tool(f, fresh) for f in features]
        inputs = summary.Inputs(phase=snap.get("phase", ""), progress=float(snap.get("progress") or 0),
                                steps=snap.get("steps") or {}, step_titles=self.step_titles(),
                                components=snap.get("components") or {}, features=features,
                                update=snap.get("update") or {}, approvals=self.approvals(),
                                awakening_left=journey.get("total", 0) - journey.get("finished", 0))
        active = sum(1 for t in tools if t["enabled"])
        return {
            "phase": inputs.phase,
            "tone": summary.tone(inputs),
            "health": summary.health(inputs.components),
            "headline": summary.headline(inputs, active, len(tools)),
            "todos": [t.as_dict() for t in summary.todos(inputs)],
            "counts": {"total": len(tools), "active": active,
                       "zones": {z: sum(1 for t in tools if t["zone"] == z) for z in ZONES}},
            "awakening": journey,
            "families": FAMILIES,
            "fresh": sorted(({"id": t["id"], "name": t["name"], "icon": t["icon"], "badge": t["badge"], "since": t["since"],
                              "level": t["level"]} for t in tools if t["badge"]), key=lambda t: -t["since"]),
            "tools": tools,
            "components": [{"id": k, "label": v.get("label", k), "status": v.get("status", ""), "detail": v.get("detail", ""),
                            "on_demand": bool(v.get("on_demand"))} for k, v in inputs.components.items()],
        }
