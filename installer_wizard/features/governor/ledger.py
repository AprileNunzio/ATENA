import logging
import sqlite3
import threading
import time
from pathlib import Path

log = logging.getLogger("atena.governor")
SCHEMA = """CREATE TABLE IF NOT EXISTS usage (
  minute INTEGER NOT NULL, component TEXT NOT NULL, kind TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0, cpu_ms REAL NOT NULL DEFAULT 0, wall_ms REAL NOT NULL DEFAULT 0,
  max_wall_ms REAL NOT NULL DEFAULT 0, size_sum REAL NOT NULL DEFAULT 0, mem_kb REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (minute, component, kind))"""
SAMPLES = """CREATE TABLE IF NOT EXISTS samples (
  minute INTEGER PRIMARY KEY, cpu REAL, mem REAL, swap REAL, load REAL, pressure REAL, temp REAL, n INTEGER)"""


class Ledger:

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.db: sqlite3.Connection | None = None
        self.pruned = 0.0

    def _conn(self) -> sqlite3.Connection:
        if self.db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, check_same_thread=False)
            self.db.execute(SCHEMA)
            self.db.execute(SAMPLES)
            self.db.commit()
        return self.db

    def record(self, component: str, kind: str, cpu_ms: float, wall_ms: float, size: float = 0.0, mem_kb: float = 0.0) -> None:
        minute = int(time.time() // 60)
        try:
            with self.lock:
                db = self._conn()
                db.execute(
                    "INSERT INTO usage(minute, component, kind, n, cpu_ms, wall_ms, max_wall_ms, size_sum, mem_kb) "
                    "VALUES(?,?,?,1,?,?,?,?,?) "
                    "ON CONFLICT(minute, component, kind) DO UPDATE SET n=n+1, cpu_ms=cpu_ms+excluded.cpu_ms, "
                    "wall_ms=wall_ms+excluded.wall_ms, max_wall_ms=MAX(max_wall_ms, excluded.max_wall_ms), "
                    "size_sum=size_sum+excluded.size_sum, mem_kb=MAX(mem_kb, excluded.mem_kb)",
                    (minute, component[:80], kind[:20], cpu_ms, wall_ms, wall_ms, size, mem_kb))
                db.commit()
        except sqlite3.Error as exc:
            log.warning("Costo di «%s» non registrato: %s", component, exc)

    def sample(self, cpu: float, mem: float, swap: float, load: float, pressure: float, temp: float | None) -> None:
        minute = int(time.time() // 60)
        try:
            with self.lock:
                db = self._conn()
                db.execute(
                    "INSERT INTO samples(minute, cpu, mem, swap, load, pressure, temp, n) VALUES(?,?,?,?,?,?,?,1) "
                    "ON CONFLICT(minute) DO UPDATE SET cpu=(cpu*n+excluded.cpu)/(n+1), mem=(mem*n+excluded.mem)/(n+1), "
                    "swap=(swap*n+excluded.swap)/(n+1), load=(load*n+excluded.load)/(n+1), "
                    "pressure=MAX(pressure, excluded.pressure), temp=COALESCE(excluded.temp, temp), n=n+1",
                    (minute, cpu, mem, swap, load, pressure, temp))
                db.commit()
        except sqlite3.Error as exc:
            log.warning("Campione di risorse non registrato: %s", exc)

    def top(self, minutes: int = 60, limit: int = 20) -> list[dict]:
        since = int(time.time() // 60) - minutes
        try:
            with self.lock:
                rows = self._conn().execute(
                    "SELECT component, kind, SUM(n), SUM(cpu_ms), SUM(wall_ms), MAX(max_wall_ms), SUM(size_sum), MAX(mem_kb) "
                    "FROM usage WHERE minute>=? GROUP BY component, kind ORDER BY SUM(wall_ms) DESC LIMIT ?",
                    (since, limit)).fetchall()
        except sqlite3.Error as exc:
            log.warning("Costi non letti: %s", exc)
            return []
        return [{"component": r[0], "kind": r[1], "calls": r[2], "cpu_ms": round(r[3], 1), "wall_ms": round(r[4], 1),
                 "avg_wall_ms": round(r[4] / max(1, r[2]), 1), "max_wall_ms": round(r[5], 1),
                 "avg_size": round(r[6] / max(1, r[2]), 1), "mem_kb": int(r[7])} for r in rows]

    def history(self, minutes: int = 120) -> list[dict]:
        since = int(time.time() // 60) - minutes
        try:
            with self.lock:
                rows = self._conn().execute(
                    "SELECT minute, cpu, mem, swap, load, pressure, temp FROM samples WHERE minute>=? ORDER BY minute",
                    (since,)).fetchall()
        except sqlite3.Error as exc:
            log.warning("Storico delle risorse non letto: %s", exc)
            return []
        return [{"t": r[0] * 60, "cpu": round(r[1], 1), "mem": round(r[2], 1), "swap": round(r[3], 1),
                 "load": round(r[4], 2), "pressure": round(r[5], 1), "temp": r[6]} for r in rows]

    def estimate(self, component: str, kind: str | None = None, size: float = 0.0) -> dict | None:
        since = int(time.time() // 60) - 7 * 1440
        query = ("SELECT SUM(n), SUM(cpu_ms), SUM(wall_ms), MAX(max_wall_ms), SUM(size_sum) "
                 "FROM usage WHERE component=? AND minute>=?")
        args: list = [component, since]
        if kind:
            query += " AND kind=?"
            args.append(kind)
        try:
            with self.lock:
                n, cpu, wall, peak, sizes = self._conn().execute(query, args).fetchone()
        except sqlite3.Error as exc:
            log.warning("Stima del costo non letta: %s", exc)
            return None
        if not n:
            return None
        avg_wall, avg_size = wall / n, sizes / n
        scale = size / avg_size if size and avg_size > 0 else 1.0
        return {"avg_wall_ms": round(avg_wall * scale, 1), "avg_cpu_ms": round(cpu / n * scale, 1),
                "max_wall_ms": round(peak, 1), "samples": n}

    def prune(self, days: float) -> None:
        if time.time() - self.pruned < 3600:
            return
        self.pruned = time.time()
        cutoff = int(time.time() // 60) - int(days * 1440)
        try:
            with self.lock:
                db = self._conn()
                db.execute("DELETE FROM usage WHERE minute<?", (cutoff,))
                db.execute("DELETE FROM samples WHERE minute<?", (cutoff,))
                db.commit()
        except sqlite3.Error as exc:
            log.warning("Pulizia delle statistiche non riuscita: %s", exc)

    def clear(self) -> None:
        try:
            with self.lock:
                db = self._conn()
                db.execute("DELETE FROM usage")
                db.execute("DELETE FROM samples")
                db.commit()
        except sqlite3.Error as exc:
            log.warning("Statistiche non azzerate: %s", exc)
