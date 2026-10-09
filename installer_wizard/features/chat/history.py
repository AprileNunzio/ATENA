import logging
import os
from contextlib import contextmanager
import sqlite3
import threading
import time
from pathlib import Path

from config import STATE_DIR

HISTORY_DB = STATE_DIR / "chat" / "dialogue.db"
RETENTION = 7 * 86400
log = logging.getLogger("atena.chat")


class HistoryStore:

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.broken = False
        self.writes = 0

    def _db(self) -> Path:
        return self.path or HISTORY_DB

    def _connect(self) -> sqlite3.Connection:
        path = self._db()
        path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not path.exists()
        conn = sqlite3.connect(path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS turns (device TEXT NOT NULL, text TEXT NOT NULL, reply TEXT NOT NULL, "
                     "intent TEXT NOT NULL, at REAL NOT NULL)")
        conn.execute("CREATE INDEX IF NOT EXISTS turns_device_at ON turns (device, at)")
        if fresh:
            os.chmod(path, 0o600)
        return conn

    @contextmanager
    def _session(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add(self, device: str, text: str, reply: str, intent: str, at: float) -> None:
        if self.broken:
            return
        try:
            with self.lock, self._session() as conn:
                conn.execute("INSERT INTO turns VALUES (?, ?, ?, ?, ?)", (device, text, reply, intent, at))
                self.writes += 1
                if self.writes % 50 == 1:
                    conn.execute("DELETE FROM turns WHERE at < ?", (time.time() - RETENTION,))
        except (sqlite3.Error, OSError, ValueError) as exc:
            self.broken = True
            log.warning("Storia della conversazione solo in memoria: %s", exc)

    def recent(self, device: str, since: float, limit: int) -> list[tuple[str, str, str, float]]:
        if self.broken:
            return []
        try:
            with self.lock, self._session() as conn:
                rows = conn.execute("SELECT text, reply, intent, at FROM turns WHERE device = ? AND at >= ? "
                                    "ORDER BY at DESC LIMIT ?", (device, since, limit)).fetchall()
        except (sqlite3.Error, OSError, ValueError) as exc:
            self.broken = True
            log.warning("Storia della conversazione non leggibile: %s", exc)
            return []
        return list(reversed(rows))

    def forget(self, device: str = "") -> int:
        try:
            with self.lock, self._session() as conn:
                cursor = conn.execute("DELETE FROM turns WHERE device = ?", (device,)) if device else conn.execute("DELETE FROM turns")
                return cursor.rowcount
        except (sqlite3.Error, OSError, ValueError) as exc:
            log.warning("Storia della conversazione non cancellata: %s", exc)
            return 0


history = HistoryStore()
