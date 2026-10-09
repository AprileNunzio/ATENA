import json
import time
import uuid

from config import STATE_DIR

from features.autonomy.trust import signature

FILE = STATE_DIR / "autonomy_approvals.json"
EXPIRE = 3 * 86400


def _load() -> list[dict]:
    try:
        items = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [a for a in items if time.time() - a["at"] < EXPIRE]


def _save(items: list[dict]) -> None:
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-50:], ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(FILE)


def add(title: str, summary: str, request: str, steps: list, tool: str, args: dict, routine: str = "") -> dict:
    sig = signature(tool, args)
    items = _load()
    same = next((a for a in items if a.get("sig") == sig), None)
    if same:
        return {**same, "existing": True}
    item = {"id": uuid.uuid4().hex[:6], "at": time.time(), "title": title[:100], "summary": summary[:400],
            "request": request, "steps": steps, "tool": tool, "args": args, "routine": routine, "sig": sig}
    items.append(item)
    _save(items)
    return item


def pending() -> list[dict]:
    return _load()


def take(aid: str) -> dict:
    items = _load()
    found = next((a for a in items if a["id"] == aid), None)
    if not found:
        raise KeyError(aid)
    _save([a for a in items if a["id"] != aid])
    return found


def prune(still_valid) -> int:
    items = _load()
    keep = [a for a in items if still_valid(a)]
    if len(keep) != len(items):
        _save(keep)
    return len(items) - len(keep)
