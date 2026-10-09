import threading
import time
from pathlib import Path
from typing import Callable, Protocol

from features.nexus.domain import freshness

REFRESH_SECONDS = 60


class Document(Protocol):
    def read(self) -> dict: ...

    def write(self, data: dict) -> None: ...


class FreshnessService:
    def __init__(self, fingerprint: Callable[[Path], str], document: Document, clock: Callable[[], float] = time.time) -> None:
        self.fingerprint = fingerprint
        self.document = document
        self.clock = clock
        self._records: dict[str, freshness.Record] | None = None
        self._checked = 0.0
        self._lock = threading.Lock()

    def due(self) -> bool:
        return self._records is None or self.clock() - self._checked >= REFRESH_SECONDS

    def refresh(self, folders: dict[str, Path]) -> None:
        with self._lock:
            if not self.due():
                return
            previous = self._records if self._records is not None else freshness.restore(self.document.read())
            current = {}
            for fid, folder in folders.items():
                try:
                    current[fid] = self.fingerprint(folder)
                except OSError:
                    continue
            now = self.clock()
            records = freshness.reconcile(previous, current, now)
            if records != previous:
                self.document.write({fid: rec.as_dict() for fid, rec in records.items()})
            self._records, self._checked = records, now

    def badges(self) -> dict[str, dict]:
        now = self.clock()
        return {fid: freshness.badge(rec, now) for fid, rec in (self._records or {}).items()}
