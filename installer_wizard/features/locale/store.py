import json
import logging
import re
import threading

from config import STATE_DIR

PREFS_FILE = STATE_DIR / "locale" / "prefs.json"
SCOPES = ("devices", "users", "people")
KEY = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")
FIELDS = ("ui", "reply", "teach")
log = logging.getLogger("atena.locale")


class LocaleStore:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, dict]] = {scope: {} for scope in SCOPES}
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.error("Preferenze di lingua illeggibili, riparto dai valori di sistema: %s", exc)
            return
        data = {scope: {} for scope in SCOPES}
        for scope in SCOPES:
            for key, values in (raw.get(scope) or {}).items() if isinstance(raw, dict) else ():
                if KEY.match(str(key)) and isinstance(values, dict):
                    data[scope][key] = {f: str(values[f]) for f in FIELDS if values.get(f)}
        with self._lock:
            self._data = data

    def _save(self) -> None:
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = PREFS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(PREFS_FILE)

    def entries(self, scope: str) -> list[dict]:
        with self._lock:
            return [dict(v) for v in self._data[scope].values()]

    def get(self, scope: str, key: str) -> dict:
        with self._lock:
            return dict(self._data[scope].get(key) or {})

    def put(self, scope: str, key: str, **values: str) -> dict:
        if scope not in SCOPES or not KEY.match(key or ""):
            raise ValueError(f"chiave di preferenza non valida: {scope}/{key}")
        with self._lock:
            entry = dict(self._data[scope].get(key) or {})
            for field, value in values.items():
                if field not in FIELDS:
                    raise ValueError(f"campo di preferenza sconosciuto: {field}")
                if value:
                    entry[field] = value
                else:
                    entry.pop(field, None)
            if entry:
                self._data[scope][key] = entry
            else:
                self._data[scope].pop(key, None)
            self._save()
            return dict(entry)


store = LocaleStore()
