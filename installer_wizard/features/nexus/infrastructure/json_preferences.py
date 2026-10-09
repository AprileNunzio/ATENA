import json
import re
import threading
from pathlib import Path

from sealed import write_private

MAX_USERS = 64
_USER = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class JsonPreferencesRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    @staticmethod
    def _checked(user: str) -> str:
        if not _USER.match(user or ""):
            raise ValueError("Utente non valido")
        return user

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def load(self, user: str) -> dict | None:
        with self._lock:
            return self._read().get(self._checked(user))

    def save(self, user: str, data: dict) -> None:
        user = self._checked(user)
        with self._lock:
            everyone = self._read()
            everyone[user] = data
            if len(everyone) > MAX_USERS:
                raise ValueError("Troppi utenti con preferenze salvate")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_private(self.path, json.dumps(everyone, ensure_ascii=False, indent=1).encode("utf-8"))
