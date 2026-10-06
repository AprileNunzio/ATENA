import json
import logging
import os
import threading
import time

from config import STATE_DIR, env_get

from features.twin.model import HomeState
from features.twin.rules import RULES
from features.twin.simulator import review

log = logging.getLogger("atena.twin")
SETTINGS_FILE = STATE_DIR / "twin.json"
MODES = ("enforce", "warn", "off")
HISTORY = 50


class Twin:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.history: list[dict] = []
        self.config = self._load()

    @staticmethod
    def _load() -> dict:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        rules = data.get("rules") if isinstance(data.get("rules"), dict) else {}
        return {"rules": {name: bool(rules.get(name, True)) for name in RULES}}

    def mode(self) -> str:
        value = env_get("ATENA_TWIN", "enforce")
        return value if value in MODES else "enforce"

    def rules(self) -> list[str]:
        return [name for name, on in self.config["rules"].items() if on]

    def set_rules(self, wanted: dict) -> dict:
        with self.lock:
            self.config["rules"] = {name: bool(wanted.get(name, self.config["rules"][name])) for name in RULES}
            tmp = SETTINGS_FILE.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.config, handle)
            os.replace(tmp, SETTINGS_FILE)
            return dict(self.config["rules"])

    @staticmethod
    def snapshot() -> HomeState:
        from features.automations.bus import bus
        from features.home_assistant.home import brain
        areas = {eid: e.get("area_id") or "" for eid, e in getattr(brain, "entities", {}).items()}
        return HomeState(dict(getattr(brain, "states", {})), {"people": len(bus.present), "areas": areas})

    def check(self, plan: dict, state: HomeState | None = None, correct: bool = True):
        return review(state or self.snapshot(), plan, self.rules(), correct)

    def guard(self, plan: dict, text: str, source: str) -> tuple[dict, dict | None]:
        mode = self.mode()
        if mode == "off" or not plan.get("calls"):
            return plan, None
        try:
            result = self.check(plan, correct=mode == "enforce")
        except Exception as exc:
            log.warning("Gemello digitale non disponibile: %s", exc)
            return plan, None
        verdict = {**result.to_dict(), "at": time.time(), "source": source, "text": text[:200], "mode": mode}
        if result.conflicts:
            self._remember(verdict)
        return (result.plan if mode == "enforce" else plan), verdict

    def _remember(self, verdict: dict) -> None:
        with self.lock:
            self.history = ([verdict] + self.history)[:HISTORY]
        try:
            from atena_bus import BusError, atena_bus
            atena_bus.publish("twin.verdict", verdict, origin="twin")
        except (ImportError, BusError) as exc:
            log.debug("Verdetto del gemello non pubblicato: %s", exc)


twin = Twin()
