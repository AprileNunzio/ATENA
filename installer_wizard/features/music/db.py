import logging
import sqlite3
import threading
from pathlib import Path

from features.music import layout

log = logging.getLogger("atena.music")
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS tracks (
      id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, mtime REAL NOT NULL, size INTEGER NOT NULL,
      title TEXT NOT NULL, artist TEXT NOT NULL, album_artist TEXT NOT NULL, album TEXT NOT NULL,
      track_no INTEGER DEFAULT 0, disc_no INTEGER DEFAULT 1, year INTEGER DEFAULT 0, genre TEXT DEFAULT '',
      duration REAL DEFAULT 0, bitrate INTEGER DEFAULT 0, cover INTEGER DEFAULT 0,
      album_key TEXT NOT NULL, artist_key TEXT NOT NULL, added REAL NOT NULL,
      plays INTEGER DEFAULT 0, last_played REAL DEFAULT 0, fingerprint TEXT DEFAULT '')""",
    "CREATE INDEX IF NOT EXISTS tracks_album ON tracks(album_key, disc_no, track_no)",
    "CREATE INDEX IF NOT EXISTS tracks_artist ON tracks(artist_key)",
    "CREATE INDEX IF NOT EXISTS tracks_added ON tracks(added)",
    "CREATE INDEX IF NOT EXISTS tracks_fp ON tracks(fingerprint)",
    """CREATE TABLE IF NOT EXISTS likes (user TEXT NOT NULL, track_id INTEGER NOT NULL, at REAL NOT NULL,
      PRIMARY KEY (user, track_id))""",
    """CREATE TABLE IF NOT EXISTS ratings (user TEXT NOT NULL, track_id INTEGER NOT NULL, stars INTEGER NOT NULL,
      PRIMARY KEY (user, track_id))""",
    """CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, user TEXT NOT NULL, track_id INTEGER NOT NULL,
      at REAL NOT NULL, secs REAL DEFAULT 0, done INTEGER DEFAULT 0, source TEXT DEFAULT '')""",
    "CREATE INDEX IF NOT EXISTS history_user ON history(user, at)",
    """CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, name TEXT NOT NULL, owner TEXT NOT NULL,
      created REAL NOT NULL, updated REAL NOT NULL, kind TEXT NOT NULL DEFAULT 'manual', rule TEXT DEFAULT '',
      description TEXT DEFAULT '', shared INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS playlist_tracks (playlist_id INTEGER NOT NULL, pos INTEGER NOT NULL,
      track_id INTEGER NOT NULL, PRIMARY KEY (playlist_id, pos))""",
    """CREATE TABLE IF NOT EXISTS lookups (track_id INTEGER NOT NULL, kind TEXT NOT NULL, at REAL NOT NULL,
      PRIMARY KEY (track_id, kind))""",
    """CREATE TABLE IF NOT EXISTS lookups (track_id INTEGER NOT NULL, kind TEXT NOT NULL, at REAL NOT NULL,
      PRIMARY KEY (track_id, kind))""",
    """CREATE TABLE IF NOT EXISTS hints (path TEXT PRIMARY KEY, data TEXT NOT NULL, at REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shares (token TEXT PRIMARY KEY, kind TEXT NOT NULL, ref TEXT NOT NULL,
      owner TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, uses INTEGER DEFAULT 0)""",
)


class Database:

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.lock = threading.RLock()
        self.conn: sqlite3.Connection | None = None
        self.fts = False

    def open(self) -> sqlite3.Connection:
        if self.conn is None:
            target = self.path or layout.DB_FILE
            target.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(target, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            for statement in SCHEMA:
                conn.execute(statement)
            self.fts = self.setup_fts(conn)
            conn.commit()
            self.conn = conn
        return self.conn

    @staticmethod
    def setup_fts(conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(title, artist, album, genre, tokenize='unicode61 remove_diacritics 2')")
        except sqlite3.OperationalError as exc:
            log.warning("Ricerca veloce non disponibile (%s): uso la ricerca semplice", exc)
            return False
        return True

    def rows(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.open().execute(sql, params).fetchall()]

    def row(self, sql: str, params: tuple = ()) -> dict | None:
        with self.lock:
            found = self.open().execute(sql, params).fetchone()
        return dict(found) if found else None

    def scalar(self, sql: str, params: tuple = (), default=0):
        with self.lock:
            found = self.open().execute(sql, params).fetchone()
        return found[0] if found and found[0] is not None else default

    def run(self, sql: str, params: tuple = ()) -> int:
        with self.lock:
            conn = self.open()
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.lastrowid or cursor.rowcount

    def many(self, sql: str, rows: list) -> None:
        with self.lock:
            conn = self.open()
            conn.executemany(sql, rows)
            conn.commit()

    def transaction(self, work) -> None:
        with self.lock:
            conn = self.open()
            try:
                work(conn)
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
                raise

    def close(self) -> None:
        with self.lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None


db = Database()
