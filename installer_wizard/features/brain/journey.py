import time
from collections import OrderedDict

MAX_JOURNEYS = 12
MAX_NODES = 400
MAX_EDGES = 900
_NODE_KEYS = ("i", "p", "k", "n", "s", "a", "b", "d")


def _node(raw) -> dict | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("i"), int):
        return None
    out = {key: raw.get(key) for key in _NODE_KEYS}
    out["n"], out["d"], out["k"], out["s"] = (str(out[key] or "")[:1200] for key in ("n", "d", "k", "s"))
    out["n"] = out["n"][:90]
    return out


class JourneyStore:
    """Percorsi completi delle ultime domande, ricevuti dal Core e mostrati nella home."""

    def __init__(self) -> None:
        self._items: OrderedDict[str, dict] = OrderedDict()
        self.seq = 0

    def put(self, key: str, data: dict) -> None:
        if not isinstance(data, dict):
            return
        nodes = [n for n in (_node(r) for r in (data.get("nodes") or [])[:MAX_NODES]) if n]
        edges = [[e[0], e[1], str(e[2])[:12], str(e[3])[:80]] for e in (data.get("edges") or [])[:MAX_EDGES]
                 if isinstance(e, list) and len(e) >= 4 and isinstance(e[0], int) and isinstance(e[1], int)]
        item = {"id": key, "query": str(data.get("query") or "")[:400], "who": str(data.get("who") or "")[:80],
                "state": str(data.get("state") or "running")[:12], "answer": str(data.get("answer") or "")[:800],
                "agent": str(data.get("agent") or "")[:80], "started": data.get("started") or time.time(),
                "elapsed": data.get("elapsed") or 0, "nodes": nodes, "edges": edges}
        self._items[key] = item
        self._items.move_to_end(key)
        while len(self._items) > MAX_JOURNEYS:
            self._items.popitem(last=False)
        self.seq += 1

    def snapshot(self) -> dict:
        return {"seq": self.seq, "journeys": list(reversed(self._items.values()))}


journeys = JourneyStore()
