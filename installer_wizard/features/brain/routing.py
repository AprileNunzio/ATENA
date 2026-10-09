import asyncio
import json
import os
import time
from pathlib import Path
from typing import Mapping

from config import STATE_DIR

from features.brain import assignments as model
from features.brain import scope
from features.brain.assignments import Assignment
from features.brain.brains import brains
from features.brain.components import COMPONENTS
from features.brain.keepalive import keep_alive_policy
from features.brain.tuning import Tuning

ROUTES_VERSION = 1


class AssignmentService:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._store = directory / "assignments.json"
        self._routes = directory / "routes.json"
        self._cache: tuple[float, dict[str, Assignment]] = (-1.0, {})
        self._published: dict = {}

    def assignments(self) -> dict[str, Assignment]:
        try:
            stamp = self._store.stat().st_mtime_ns
        except OSError:
            return {}
        if stamp != self._cache[0]:
            self._cache = (stamp, model.load(self._store.read_text(encoding="utf-8")))
        return dict(self._cache[1])

    def save(self, updates: Mapping[str, Assignment | None]) -> dict[str, Assignment]:
        current = self.assignments()
        for component_id, assignment in updates.items():
            if assignment is None or assignment.empty:
                current.pop(component_id, None)
            else:
                current[component_id] = assignment
        self._write(self._store, model.dump(current))
        self._cache = (-1.0, {})
        self.publish()
        return self.assignments()

    def tuning(self, component_id: str) -> Tuning:
        own = self.assignments().get(component_id)
        return own.tuning if own else Tuning()

    def role_orders(self) -> dict[str, list[str]]:
        return brains.orders()

    def _keep(self, component_id: str, assignments: Mapping[str, Assignment], known: set[str]):
        role_scope = brains.config()[f"{model.effective_role(component_id, assignments)}_scope"]
        return lambda ref: scope.allowed(ref, role_scope) and brains.usable(ref, known)

    def chain(self, component_id: str, installed: set[str] | None = None) -> list[str]:
        known = installed if installed is not None else set()
        assignments = self.assignments()
        return model.resolve(component_id, assignments, self.role_orders(), self._keep(component_id, assignments, known))

    def chains(self) -> dict[str, list[str]]:
        assignments, orders = self.assignments(), self.role_orders()
        return {c.id: model.resolve(c.id, assignments, orders, self._keep(c.id, assignments, set())) for c in COMPONENTS}

    def publish(self) -> None:
        assignments = self.assignments()
        payload = {"version": ROUTES_VERSION, "components": self.chains(), "explicit": sorted(assignments),
                   "keep_alive": keep_alive_policy.overrides(),
                   "tuning": {cid: a.tuning.to_json() for cid, a in sorted(assignments.items()) if not a.tuning.empty}}
        if payload == self._published and self._routes.exists():
            return
        self._write(self._routes, json.dumps({**payload, "updated": int(time.time())}, ensure_ascii=False, separators=(",", ":")))
        self._published = payload

    def overview(self, installed: set[str]) -> list[dict]:
        from features.brain.trace import trace
        assignments, orders, stats = self.assignments(), self.role_orders(), trace.summary()
        rows = []
        for component in COMPONENTS:
            own = assignments.get(component.id)
            chain = model.resolve(component.id, assignments, orders)
            rows.append({
                "id": component.id, "label": component.label, "group": component.group, "hint": component.hint,
                "side": component.side, "default_role": component.role,
                "role": model.effective_role(component.id, assignments),
                "assignment": own.to_json() if own else {"role": "", "order": [], "mode": "inherit"},
                "chain": [{**brains.describe(ref), "available": brains.usable(ref, installed)} for ref in chain],
                "stats": stats.get(component.id),
            })
        return rows

    def _write(self, path: Path, text: str) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._dir, 0o755)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(text + "\n", encoding="utf-8")
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)


assignment_service = AssignmentService(STATE_DIR / "brain")
brains.on_change(assignment_service.publish)


async def run(interval_seconds: int = 60) -> None:
    while True:
        try:
            assignment_service.publish()
        except OSError:
            pass
        await asyncio.sleep(interval_seconds)
