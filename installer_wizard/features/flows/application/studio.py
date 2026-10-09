import time
from typing import Callable

from features.flows.application.ports import Settings, Verifier, VersionStore
from features.flows.domain import draft as drafts
from features.flows.domain.catalog import EDGES, NODES, TEMPLATES, template


class ConfirmationRequired(PermissionError):
    pass


class Studio:
    def __init__(self, settings: Settings, store: VersionStore, verifier: Verifier, clock: Callable[[], float] = time.time) -> None:
        self.settings = settings
        self.store = store
        self.verifier = verifier
        self.clock = clock

    def _current(self) -> tuple[dict, dict]:
        settings = self.settings.read()
        return settings, drafts.infer(settings)

    def _draft(self, current: dict) -> drafts.Draft:
        saved = self.store.draft()
        if saved:
            try:
                return drafts.parse(saved, current)
            except ValueError:
                pass
        return drafts.initial(current)

    def _view(self, settings: dict, current: dict, draft: drafts.Draft) -> dict:
        return {
            "draft": draft.as_dict(),
            "current": current,
            "pending": drafts.changes(draft.picks, settings),
            "traits": {"draft": drafts.traits(draft.picks), "current": drafts.traits({**current}),
                       "default": drafts.traits(template("default"))},
            "estimate": drafts.estimate(draft.picks),
        }

    def studio(self) -> dict:
        settings, current = self._current()
        return {
            "nodes": [n.as_dict() for n in NODES],
            "edges": [list(e) for e in EDGES],
            "templates": {k: {"name": v["name"], "hint": v["hint"], "picks": template(k)} for k, v in TEMPLATES.items()},
            "versions": self.store.versions(),
            **self._view(settings, current, self._draft(current)),
        }

    def save_draft(self, raw) -> dict:
        settings, current = self._current()
        draft = drafts.parse(raw, current)
        self.store.save_draft(draft.as_dict())
        return self._view(settings, current, draft)

    def discard_draft(self) -> dict:
        self.store.save_draft(None)
        settings, current = self._current()
        return self._view(settings, current, drafts.initial(current))

    async def _confirm(self, user: str, password, ip: str) -> None:
        if not isinstance(password, str) or not password or not await self.verifier.confirm(user, password, ip):
            raise ConfirmationRequired("Password non corretta: conferma la tua identità per cambiare il modo di ragionare")

    async def _apply(self, draft: drafts.Draft, user: str, note: str) -> dict:
        settings, _ = self._current()
        updates = drafts.changes(draft.picks, settings)
        applying = await self.settings.apply(updates, user) if updates else []
        version = self.store.append({"picks": draft.picks, "positions": draft.as_dict()["positions"], "template": draft.template,
                                     "author": user, "at": self.clock(), "note": note, "changes": sorted(updates)})
        self.store.save_draft(None)
        return {"version": version, "applying": applying, "changed": sorted(updates)}

    async def publish(self, user: str, password, ip: str) -> dict:
        await self._confirm(user, password, ip)
        _, current = self._current()
        return await self._apply(self._draft(current), user, "Pubblicazione")

    async def rollback(self, number: int, user: str, password, ip: str) -> dict:
        await self._confirm(user, password, ip)
        target = next((v for v in self.store.versions() if v["version"] == number), None)
        if target is None:
            raise LookupError(number)
        _, current = self._current()
        draft = drafts.parse({"picks": target["picks"], "positions": target.get("positions", {}),
                              "template": target.get("template", "")}, current)
        return await self._apply(draft, user, f"Ripristino della versione {number}")
