import json
import threading
from pathlib import Path

from sealed import write_private


class JsonDocument:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def read(self) -> dict:
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
            return data if isinstance(data, dict) else {}

    def write(self, data: dict) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_private(self.path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))
