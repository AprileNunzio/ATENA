import sqlite3
import threading
import time

from features.nvr.search import Query

SCHEMA = """CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, at REAL NOT NULL, camera TEXT NOT NULL, label TEXT NOT NULL, score REAL NOT NULL,
  source TEXT NOT NULL, zone TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '')"""
MAX_RESULTS = 200


class EventStore:
    def __init__(self, path) -> None:
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute(SCHEMA)
        self.db.execute("CREATE INDEX IF NOT EXISTS ev_at ON events(at)")
        self.db.execute("CREATE INDEX IF NOT EXISTS ev_camera ON events(camera, at)")
        self.db.commit()

    def add(self, event: dict) -> bool:
        row = (str(event["id"])[:80], float(event["at"]), str(event["camera"])[:80], str(event["label"])[:40],
               max(0.0, min(1.0, float(event.get("score", 0.0)))), str(event.get("source", ""))[:20],
               str(event.get("zone", ""))[:80], str(event.get("text", ""))[:300])
        with self.lock:
            cur = self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)", row)
            self.db.commit()
            return cur.rowcount == 1

    def search(self, query: Query, limit: int = 50) -> list[dict]:
        sql = "SELECT id, at, camera, label, score, source, zone, text FROM events WHERE at >= ? AND at <= ?"
        args: list = [query.since, query.until]
        if query.labels:
            sql += f" AND label IN ({','.join('?' * len(query.labels))})"
            args += sorted(query.labels)
        for term in query.terms:
            sql += " AND (camera LIKE ? ESCAPE '!' OR zone LIKE ? ESCAPE '!' OR text LIKE ? ESCAPE '!')"
            like = "%" + term.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            args += [like, like, like]
        sql += " ORDER BY at DESC LIMIT ?"
        args.append(max(1, min(MAX_RESULTS, limit)))
        with self.lock:
            rows = self.db.execute(sql, args).fetchall()
        keys = ("id", "at", "camera", "label", "score", "source", "zone", "text")
        return [dict(zip(keys, r)) for r in rows]

    def counts(self, since: float) -> dict:
        with self.lock:
            rows = self.db.execute("SELECT label, COUNT(*) FROM events WHERE at >= ? GROUP BY label", (since,)).fetchall()
        return {label: n for label, n in rows}

    def prune(self, days: int) -> int:
        with self.lock:
            cur = self.db.execute("DELETE FROM events WHERE at < ?", (time.time() - days * 86400,))
            self.db.commit()
            return cur.rowcount

    def clear(self) -> None:
        with self.lock:
            self.db.execute("DELETE FROM events")
            self.db.commit()

    def close(self) -> None:
        with self.lock:
            self.db.close()
