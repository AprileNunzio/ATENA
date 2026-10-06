import sqlite3
import json
import time
import logging

log = logging.getLogger("atena.event_sourcing")

class TimeTravelLedger:
    """
    Motore Event Sourcing di Atena.
    Tutte le azioni sono immutabili e memorizzate come stream di eventi.
    Permette il "Time-Travel Debugging" (rewind del sistema).
    """
    def __init__(self, db_path="atena_ledger.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    aggregate_id TEXT,
                    event_type TEXT,
                    payload JSON
                )
            ''')
            conn.commit()

    def append_event(self, aggregate_id: str, event_type: str, payload: dict):
        """Aggiunge un evento immutabile al ledger."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO events (timestamp, aggregate_id, event_type, payload) VALUES (?, ?, ?, ?)",
                (time.time(), aggregate_id, event_type, json.dumps(payload))
            )
            conn.commit()
        log.debug(f"Event Appended: {event_type} on {aggregate_id}")

    def replay_to_timestamp(self, target_timestamp: float):
        """
        Riavvolge il sistema ricostruendo lo stato ESATTAMENTE com'era a un dato istante.
        Ritorna lo stato aggregato calcolato.
        """
        log.warning(f"INIZIO TIME-TRAVEL. Ricostruzione stato al timestamp {target_timestamp}...")
        state = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT aggregate_id, event_type, payload FROM events WHERE timestamp <= ? ORDER BY timestamp ASC",
                (target_timestamp,)
            )
            for row in cursor.fetchall():
                agg_id, e_type, payload_str = row
                payload = json.loads(payload_str)
                # Apply event mutators dynamically
                if agg_id not in state:
                    state[agg_id] = {}
                state[agg_id].update(payload)
                
        return state

ledger = TimeTravelLedger()
