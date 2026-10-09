import threading
import time
from typing import Callable, Protocol

from features.nexus.domain import awakening

SENSES = ("vision", "ear", "hands")


class Document(Protocol):
    def read(self) -> dict: ...

    def write(self, data: dict) -> None: ...


class AwakeningService:
    def __init__(self, document: Document, env: Callable[[], dict], catalog: Callable[[], dict], brain_mode: Callable[[], str],
                 clock: Callable[[], float] = time.time) -> None:
        self.document = document
        self.env = env
        self.catalog = catalog
        self.brain_mode = brain_mode
        self.clock = clock
        self._lock = threading.Lock()

    def _marks(self) -> dict[str, awakening.Mark]:
        return awakening.restore(self.document.read().get("steps"))

    def progress(self) -> dict:
        return awakening.progress(self._marks())

    def _current(self) -> dict:
        env = self.env()
        features = {f["id"]: f for f in self.catalog().get("features", [])}

        def mode(fid: str) -> str:
            return (features.get(fid, {}).get("state") or {}).get("mode", "")

        home_values = features.get("home_assistant", {}).get("values") or {}
        agent_values = features.get("agent", {}).get("values") or {}
        return {
            "name": env.get("ATENA_USER_NAME", ""),
            "lang": env.get("ATENA_UI_LANG", "") or "it",
            "brain": self.brain_mode(),
            "ollama_url": env.get("ATENA_OLLAMA_URL", ""),
            "senses": {fid: mode(fid) for fid in SENSES if fid in features},
            "home": {"available": "home_assistant" in features, "connected": bool(home_values.get("HOME_ASSISTANT_URL")),
                     "url": home_values.get("HOME_ASSISTANT_URL", "")},
            "trust": awakening.trust_profile(mode("autonomy"), str(agent_values.get("ATENA_AGENT_ACCESS", ""))),
        }

    def state(self) -> dict:
        marks = self._marks()
        return {"steps": [{"id": s, **(marks[s].as_dict() if s in marks else {"status": "", "at": 0, "note": ""})}
                          for s in awakening.STEPS],
                "progress": awakening.progress(marks), "current": self._current(), "profiles": awakening.TRUST_PROFILES}

    def mark(self, body: dict) -> dict:
        with self._lock:
            marks = awakening.mark(self._marks(), body.get("step"), body.get("status"), body.get("note", ""), self.clock())
            self.document.write({"steps": {k: v.as_dict() for k, v in marks.items()}})
        return self.state()

    def reset(self) -> dict:
        with self._lock:
            self.document.write({"steps": {}})
        return self.state()
