import hashlib
import hmac
import json
import logging
import secrets
import threading
from pathlib import Path

from sealed import write_private

log = logging.getLogger("atena.flows")
MAX_VERSIONS = 50


class SignedVersionStore:
    def __init__(self, path: Path, key_path: Path) -> None:
        self.path = path
        self.key_path = key_path
        self._lock = threading.Lock()

    def _key(self) -> bytes:
        if not self.key_path.exists():
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            write_private(self.key_path, secrets.token_bytes(32))
        return self.key_path.read_bytes()

    def _sign(self, payload: dict) -> str:
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return "hmac-sha256:" + hmac.new(self._key(), body, hashlib.sha256).hexdigest()

    def _valid(self, entry: dict) -> bool:
        signature = entry.get("signature", "")
        payload = {k: v for k, v in entry.items() if k != "signature"}
        return isinstance(signature, str) and hmac.compare_digest(signature, self._sign(payload))

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_private(self.path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))

    def draft(self) -> dict | None:
        with self._lock:
            draft = self._read().get("draft")
        return draft if isinstance(draft, dict) else None

    def save_draft(self, data: dict | None) -> None:
        with self._lock:
            doc = self._read()
            doc["draft"] = data
            self._write(doc)

    def versions(self) -> list[dict]:
        with self._lock:
            entries = self._read().get("versions") or []
        valid = []
        for entry in entries:
            if isinstance(entry, dict) and self._valid(entry):
                valid.append({k: v for k, v in entry.items() if k != "signature"})
            else:
                log.warning("Versione del flusso con firma non valida ignorata")
        return sorted(valid, key=lambda v: -v.get("version", 0))

    def append(self, data: dict) -> dict:
        with self._lock:
            doc = self._read()
            entries = [e for e in doc.get("versions") or [] if isinstance(e, dict)]
            number = max((e.get("version", 0) for e in entries), default=0) + 1
            entry = {**data, "version": number}
            entries.append({**entry, "signature": self._sign(entry)})
            doc["versions"] = entries[-MAX_VERSIONS:]
            self._write(doc)
        return entry
