import itertools
import time
from collections import deque
from typing import Iterable

from features.brain.brains import brains
from features.brain.components import BY_ID

MAX_RECENT = 14
MAX_STEPS = 10
STALE_SECONDS = 600
SNIPPET = 160


class Trace:
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._active: dict[int, dict] = {}
        self._recent: deque = deque(maxlen=MAX_RECENT)
        self.seq = 0
        self.stats: dict[str, dict] = {}

    def _account(self, entry: dict, ok: bool, ms: float, error: str = "") -> None:
        row = self.stats.setdefault(entry["component"], {"calls": 0, "ok": 0, "failed": 0, "total_ms": 0.0,
                                                         "last_ms": 0, "last_model": "", "last_error": "", "last_at": 0.0})
        row["calls"] += 1
        row["ok" if ok else "failed"] += 1
        row["total_ms"] += ms
        row.update(last_ms=round(ms), last_at=time.time())
        if entry.get("model"):
            row["last_model"] = entry["model"].get("label", "")
        if error:
            row["last_error"] = error[:SNIPPET]

    def summary(self) -> dict[str, dict]:
        return {component: {"calls": r["calls"], "success": round(100 * r["ok"] / r["calls"]) if r["calls"] else 0,
                            "avg_ms": round(r["total_ms"] / r["calls"]) if r["calls"] else 0, "last_ms": r["last_ms"],
                            "last_model": r["last_model"], "last_error": r["last_error"], "last_at": r["last_at"]}
                for component, r in self.stats.items()}

    def begin(self, component: str, note: str = "", chain: Iterable[str] = ()) -> int:
        call_id = next(self._ids)
        known = BY_ID.get(component)
        entry = {"id": call_id, "component": component, "label": known.label if known else component or "Atena",
                 "started": time.time(), "state": "thinking", "model": None, "steps": [],
                 "chain": [brains.describe(ref)["label"] for ref in chain]}
        self._active[call_id] = entry
        self._step(entry, note or "ricevuta la richiesta")
        if entry["chain"]:
            self._step(entry, "catena in ordine: " + " → ".join(entry["chain"][:4]) + ("…" if len(entry["chain"]) > 4 else ""))
        self._expire()
        return call_id

    def attempt(self, call_id: int, ref: str) -> None:
        entry = self._active.get(call_id)
        if entry:
            entry["model"] = brains.describe(ref)
            self._step(entry, f"interrogo {entry['model']['label']}")

    def note(self, call_id: int, text: str) -> None:
        entry = self._active.get(call_id)
        if entry:
            self._step(entry, text)

    def failed(self, call_id: int, ref: str, reason: str) -> None:
        entry = self._active.get(call_id)
        if entry:
            self._step(entry, f"{brains.describe(ref)['label']} non ha risposto ({reason[:80]}): passo al successivo")

    def finish(self, call_id: int, ref: str, ms: float, snippet: str = "") -> None:
        entry = self._active.pop(call_id, None)
        if not entry:
            return
        entry["model"] = brains.describe(ref) if ref else None
        entry.update(state="done", ms=round(ms), snippet=" ".join(snippet.split())[:SNIPPET], ended=time.time())
        self._step(entry, f"risposta di {entry['model']['label']} in {round(ms)} ms" if ref else f"completato in {round(ms)} ms")
        self._account(entry, True, ms)
        self._recent.appendleft(entry)
        self.seq += 1

    def abort(self, call_id: int, reason: str) -> None:
        entry = self._active.pop(call_id, None)
        if not entry:
            return
        entry.update(state="failed", ms=round((time.time() - entry["started"]) * 1000), snippet=reason[:SNIPPET], ended=time.time())
        self._step(entry, f"nessun cervello ha risposto: {reason[:80]}")
        self._account(entry, False, entry["ms"], reason)
        self._recent.appendleft(entry)
        self.seq += 1

    def snapshot(self) -> dict:
        self._expire()
        now = time.time()
        active = [{**e, "elapsed_ms": round((now - e["started"]) * 1000)} for e in self._active.values()]
        return {"seq": self.seq, "active": sorted(active, key=lambda e: e["started"]), "recent": list(self._recent)}

    def _step(self, entry: dict, text: str) -> None:
        entry["steps"] = (entry["steps"] + [{"t": round(time.time() - entry["started"], 2), "text": text}])[-MAX_STEPS:]
        self.seq += 1

    def _expire(self) -> None:
        limit = time.time() - STALE_SECONDS
        for call_id in [i for i, e in self._active.items() if e["started"] < limit]:
            self.abort(call_id, "scaduta")


trace = Trace()
