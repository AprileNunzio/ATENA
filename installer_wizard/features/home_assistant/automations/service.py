import asyncio
import copy
import time
from datetime import datetime, timezone

import httpx
from config import DEMO

from features.home_assistant.automations import describe, model
from features.home_assistant.automations.demo import DEMO_AUTOMATIONS
from features.home_assistant.automations.model import AutomationError
from features.home_assistant.connection import HAError

_CACHE_TTL = 60
_PARALLEL = 8


class AutomationService:
    def __init__(self, brain) -> None:
        self.brain = brain
        self._cache: dict[str, tuple[float, dict]] = {}
        self._demo = {f"automation.{c['id']}": copy.deepcopy(c) for c in DEMO_AUTOMATIONS}
        self._demo_state = {eid: {"on": True, "last": ""} for eid in self._demo}

    def name(self, ref: str) -> str:
        entity = self.brain.entities.get(ref)
        if entity:
            return entity.get("name") or ref
        area = self.brain.areas.get(ref)
        return area["name"] if area else ref

    def _rows(self) -> list[dict]:
        if DEMO:
            return [{"entity_id": eid, "id": c["id"], "alias": c["alias"],
                     "state": "on" if self._demo_state[eid]["on"] else "off",
                     "last_triggered": self._demo_state[eid]["last"] or None, "mode": c.get("mode", "single")}
                    for eid, c in self._demo.items()]
        rows = []
        for eid, st in self.brain.states.items():
            if not eid.startswith("automation."):
                continue
            attrs = st.get("attrs") or {}
            rows.append({"entity_id": eid, "id": str(attrs.get("id") or ""), "alias": attrs.get("friendly_name") or eid,
                         "state": st.get("state"), "last_triggered": attrs.get("last_triggered"),
                         "mode": attrs.get("mode", "single")})
        return rows

    async def _config(self, entity_id: str) -> dict:
        if DEMO:
            if entity_id not in self._demo:
                raise AutomationError("Automazione sconosciuta")
            return copy.deepcopy(self._demo[entity_id])
        hit = self._cache.get(entity_id)
        if hit and time.time() - hit[0] < _CACHE_TTL:
            return copy.deepcopy(hit[1])
        try:
            result = await self.brain._call({"type": "automation/config", "entity_id": entity_id}, 15)
        except (HAError, asyncio.TimeoutError) as exc:
            raise AutomationError(f"Home Assistant non ha restituito l'automazione: {exc}") from exc
        config = (result or {}).get("config") or {}
        self._cache[entity_id] = (time.time(), config)
        return copy.deepcopy(config)

    def _invalidate(self) -> None:
        self._cache.clear()

    async def overview(self) -> list[dict]:
        rows = sorted(self._rows(), key=lambda r: str(r["alias"]).lower())
        gate = asyncio.Semaphore(_PARALLEL)

        async def enrich(row: dict) -> dict:
            async with gate:
                try:
                    config = await self._config(row["entity_id"])
                except AutomationError as exc:
                    return {**row, "summary": None, "description": "", "error": str(exc)}
            return {**row, "description": config.get("description", ""), "editable": bool(row["id"]),
                    "summary": describe.summary(config, self.name)}
        return list(await asyncio.gather(*(enrich(r) for r in rows)))

    async def get(self, entity_id: str) -> dict:
        model.check_entity(entity_id)
        config = await self._config(entity_id)
        row = next((r for r in self._rows() if r["entity_id"] == entity_id), None)
        if not row:
            raise AutomationError("Automazione sconosciuta")
        return {**row, "config": config, "summary": describe.summary(config, self.name),
                "unknown_entities": self.unknown(config)}

    def unknown(self, config: dict) -> list[str]:
        refs = {e for e in model.entity_ids(config) if "{{" not in e}
        return sorted(e for e in refs if e not in self.brain.entities and e not in self.brain.states)

    async def _rest(self, method: str, auto_id: str, body: dict | None = None) -> None:
        s = self.brain.settings()
        if not s["url"] or not s["token"]:
            raise AutomationError("Home Assistant non è configurato")
        url = f"{s['url']}/api/config/automation/config/{auto_id}"
        try:
            async with httpx.AsyncClient(timeout=20, verify=s["verify_ssl"]) as client:
                r = await client.request(method, url, json=body, headers={"Authorization": f"Bearer {s['token']}"})
        except httpx.HTTPError as exc:
            raise AutomationError(f"Home Assistant non raggiungibile: {type(exc).__name__}") from exc
        if r.status_code == 401:
            raise AutomationError("Home Assistant ha rifiutato il token: serve un utente amministratore")
        if r.status_code >= 400:
            detail = r.json().get("message", "") if "json" in r.headers.get("content-type", "") else r.text[:200]
            raise AutomationError(f"Home Assistant ha rifiutato l'automazione: {detail or r.status_code}")

    async def save(self, auto_id: str | None, raw: dict) -> dict:
        config = model.normalize(raw)
        auto_id = model.check_id(auto_id) if auto_id else model.new_id()
        config = {"id": auto_id, **config}
        if DEMO:
            eid = next((e for e, c in self._demo.items() if c["id"] == auto_id), None) or f"automation.{auto_id}"
            self._demo[eid] = config
            self._demo_state.setdefault(eid, {"on": True, "last": ""})
        else:
            await self._rest("POST", auto_id, config)
            self._invalidate()
        return {"id": auto_id, "config": config, "summary": describe.summary(config, self.name),
                "unknown_entities": self.unknown(config)}

    async def delete(self, auto_id: str) -> None:
        model.check_id(auto_id)
        if DEMO:
            self._demo = {e: c for e, c in self._demo.items() if c["id"] != auto_id}
            return
        await self._rest("DELETE", auto_id)
        self._invalidate()

    async def _service(self, service: str, entity_id: str, data: dict | None = None) -> None:
        model.check_entity(entity_id)
        if DEMO:
            if entity_id not in self._demo_state:
                raise AutomationError("Automazione sconosciuta")
            if service in ("turn_on", "turn_off"):
                self._demo_state[entity_id]["on"] = service == "turn_on"
            if service == "trigger":
                self._demo_state[entity_id]["last"] = datetime.now(timezone.utc).isoformat()
            return
        try:
            await self.brain._call({"type": "call_service", "domain": "automation", "service": service,
                                    "service_data": data or {}, "target": {"entity_id": [entity_id]}}, 15)
        except (HAError, asyncio.TimeoutError) as exc:
            raise AutomationError(f"Comando non riuscito: {exc}") from exc

    async def toggle(self, entity_id: str, on: bool) -> None:
        await self._service("turn_on" if on else "turn_off", entity_id)

    async def run(self, entity_id: str) -> None:
        await self._service("trigger", entity_id, {"skip_condition": True})

    async def traces(self, auto_id: str) -> list[dict]:
        model.check_id(auto_id)
        if DEMO:
            return []
        try:
            rows = await self.brain._call({"type": "trace/list", "domain": "automation", "item_id": auto_id}, 15)
        except (HAError, asyncio.TimeoutError) as exc:
            raise AutomationError(f"Tracce non disponibili: {exc}") from exc
        out = []
        for t in sorted(rows or [], key=lambda x: (x.get("timestamp") or {}).get("start", ""), reverse=True)[:20]:
            out.append({"run_id": t.get("run_id"), "start": (t.get("timestamp") or {}).get("start"),
                        "finish": (t.get("timestamp") or {}).get("finish"), "state": t.get("state"),
                        "result": t.get("script_execution"), "trigger": t.get("trigger"), "error": t.get("error")})
        return out
