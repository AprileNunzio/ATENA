import hashlib
import hmac
import json
import secrets
import time

from config import STATE_DIR

FILE = STATE_DIR / "mcp_tokens.json"
MAX_TOKENS = 20
FAILS: dict[str, list[float]] = {}


def _load() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(FILE)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(label: str, risky: bool = False) -> dict:
    data = _load()
    if len(data) >= MAX_TOKENS:
        raise ValueError("Troppi token: revocane qualcuno")
    token = "jv_" + secrets.token_urlsafe(32)
    data[digest(token)[:16]] = {"hash": digest(token), "label": str(label).strip()[:60] or "client", "risky": bool(risky), "created": time.time(), "used": 0}
    _save(data)
    return {"token": token, "id": digest(token)[:16]}


def listing() -> list[dict]:
    return [{"id": k, "label": v["label"], "risky": v["risky"], "created": v["created"], "used": v["used"]} for k, v in _load().items()]


def revoke(token_id: str) -> bool:
    data = _load()
    found = data.pop(token_id, None) is not None
    if found:
        _save(data)
    return found


def locked(ip: str) -> bool:
    now = time.time()
    FAILS[ip] = [t for t in FAILS.get(ip, []) if now - t < 300]
    return len(FAILS[ip]) >= 8


def check(header: str, ip: str) -> dict | None:
    if locked(ip):
        return None
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    data = _load()
    wanted = digest(token)
    for key, row in data.items():
        if token and hmac.compare_digest(row["hash"], wanted):
            row["used"] = time.time()
            _save(data)
            return {"id": key, "label": row["label"], "risky": row["risky"]}
    FAILS.setdefault(ip, []).append(time.time())
    return None
