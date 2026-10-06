import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("atena.scheduler")
FLUSH_EVERY = 15.0


class Marks:

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, float] = {}
        self.dirty = False
        self.saved = 0.0
        self.persist = True
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.data = {str(k): float(v) for k, v in raw.get("last", {}).items()}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError) as exc:
            log.warning("Stato del pianificatore non letto (riparto da zero): %s", exc)

    def get(self, key: str) -> float | None:
        return self.data.get(key)

    def set(self, key: str, value: float, now_flush: bool = False) -> None:
        self.data[key] = value
        self.dirty = True
        if now_flush:
            self.flush(force=True)

    def prune(self, valid: set) -> None:
        stale = [k for k in self.data if k not in valid]
        for key in stale:
            del self.data[key]
        self.dirty = self.dirty or bool(stale)

    def flush(self, force: bool = False) -> None:
        if not self.persist or not self.dirty or (not force and time.time() - self.saved < FLUSH_EVERY):
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"last": self.data}), encoding="utf-8")
            os.replace(tmp, self.path)
            self.dirty = False
            self.saved = time.time()
        except OSError as exc:
            log.warning("Stato del pianificatore non salvato: %s", exc)
