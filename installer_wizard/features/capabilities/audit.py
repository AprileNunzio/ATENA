import time
from collections import deque

from state import store

RING: deque = deque(maxlen=200)
CALLS: dict[str, list[float]] = {}
WINDOW = 60.0
LIMIT = 120


def allow(token_id: str) -> bool:
    now = time.time()
    recent = [t for t in CALLS.get(token_id, []) if now - t < WINDOW]
    if len(recent) >= LIMIT:
        CALLS[token_id] = recent
        return False
    recent.append(now)
    CALLS[token_id] = recent
    return True


def record(token: dict, method: str, name: str, ok: bool, ms: float) -> None:
    row = {"at": time.time(), "client": token["label"], "method": method, "tool": name, "ok": ok, "ms": round(ms)}
    RING.append(row)
    if method == "tools/call":
        store.event("INFO" if ok else "WARN", f"MCP · {token['label']} → {name}: {'ok' if ok else 'non riuscito'} ({row['ms']} ms)", "mcp")


def recent(limit: int = 50) -> list[dict]:
    return list(RING)[-limit:]
