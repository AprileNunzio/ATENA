import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any, Callable, Dict, Iterator, Optional

GENESIS = "0" * 64
_CONTEXT = b"atena.consensus.ledger.v1"


def _canonical(record: Dict[str, Any]) -> bytes:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class VerdictLedger:
    def __init__(self, path: str, key_provider: Callable[[], str], clock: Callable[[], float] = time.time) -> None:
        self._path = path
        self._key = key_provider
        self._clock = clock
        self._lock = threading.Lock()
        self._head: Optional[str] = None

    def _mac(self, body: bytes) -> str:
        key = hmac.new(self._key().encode("utf-8"), _CONTEXT, hashlib.sha256).digest()
        return hmac.new(key, body, hashlib.sha256).hexdigest()

    def _last(self) -> str:
        if self._head is None:
            self._head = GENESIS
            for entry in self._entries():
                self._head = entry["mac"]
        return self._head

    def _entries(self) -> Iterator[Dict[str, Any]]:
        try:
            with open(self._path, encoding="utf-8") as stream:
                for line in stream:
                    if line.strip():
                        yield json.loads(line)
        except FileNotFoundError:
            return

    def append(self, event: Dict[str, Any]) -> str:
        with self._lock:
            body = {"at": self._clock(), "prev": self._last(), "event": event}
            mac = self._mac(_canonical(body))
            os.makedirs(os.path.dirname(self._path) or ".", mode=0o700, exist_ok=True)
            fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(json.dumps({**body, "mac": mac}, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._head = mac
            return mac

    def verify(self) -> bool:
        with self._lock:
            previous = GENESIS
            try:
                for entry in self._entries():
                    mac = entry.pop("mac", "")
                    if entry.get("prev") != previous or not hmac.compare_digest(self._mac(_canonical(entry)), mac):
                        return False
                    previous = mac
            except (ValueError, AttributeError):
                return False
            return True
