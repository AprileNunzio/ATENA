import hashlib
import json
import logging
import threading
import time

from config import STATE_DIR

log = logging.getLogger("atena.autonomy")
FILE = STATE_DIR / "autonomy_trust.json"
REJECT_FOR = 24 * 3600
MAX_RULES = 200


def signature(tool: str, args: dict) -> str:
    body = json.dumps({"tool": tool, "args": args}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:20]


class TrustBook:
    def __init__(self, path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except ValueError as exc:
            log.warning("Regole di fiducia illeggibili, riparto da zero: %s", exc)
            data = {}
        now = time.time()
        return {"trusted": dict(data.get("trusted") or {}),
                "rejected": {k: v for k, v in (data.get("rejected") or {}).items() if now - float(v) < REJECT_FOR}}

    def _save(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def trusted(self, tool: str, args: dict) -> bool:
        return signature(tool, args) in self._load()["trusted"]

    def rejected(self, tool: str, args: dict) -> bool:
        return signature(tool, args) in self._load()["rejected"]

    def trust(self, tool: str, args: dict, title: str, summary: str) -> None:
        with self._lock:
            data = self._load()
            data["trusted"][signature(tool, args)] = {"tool": tool, "title": title[:100], "summary": summary[:300], "at": time.time()}
            if len(data["trusted"]) > MAX_RULES:
                oldest = sorted(data["trusted"], key=lambda k: data["trusted"][k]["at"])[: len(data["trusted"]) - MAX_RULES]
                for key in oldest:
                    data["trusted"].pop(key)
            self._save(data)

    def reject(self, tool: str, args: dict) -> None:
        with self._lock:
            data = self._load()
            data["rejected"][signature(tool, args)] = time.time()
            self._save(data)

    def rules(self) -> list[dict]:
        return [{"id": k, **v} for k, v in sorted(self._load()["trusted"].items(), key=lambda kv: -kv[1]["at"])]

    def revoke(self, rule_id: str) -> bool:
        with self._lock:
            data = self._load()
            found = data["trusted"].pop(str(rule_id), None) is not None
            self._save(data)
        return found


book = TrustBook(FILE)
