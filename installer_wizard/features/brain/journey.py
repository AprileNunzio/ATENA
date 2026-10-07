import time
import uuid
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


class JourneyTracker:
    def __init__(self, store: "JourneyStore", key: str, query: str, who: str = "") -> None:
        self.store = store
        self.id = key
        self.query = query[:400]
        self.who = who[:80]
        self.state = "running"
        self.answer = ""
        self.agent = ""
        self.started = time.time()
        self.nodes: list[dict] = []
        self.edges: list[list] = []
        self._commit()

    def _rel(self) -> float:
        return round(time.time() - self.started, 2)

    def _commit(self) -> None:
        self.store.put(self.id, {
            "query": self.query,
            "who": self.who,
            "state": self.state,
            "answer": self.answer,
            "agent": self.agent,
            "started": self.started,
            "elapsed": self._rel(),
            "nodes": list(self.nodes),
            "edges": list(self.edges),
        })

    def add_node(self, kind: str, name: str, detail: str = "", state: str = "ok", parent: int | None = None) -> int:
        idx = len(self.nodes)
        rel = self._rel()
        self.nodes.append({
            "i": idx,
            "p": parent,
            "k": kind,
            "n": str(name)[:90],
            "d": str(detail)[:1200],
            "s": state,
            "a": rel,
            "b": rel,
        })
        self._commit()
        return idx

    def add_edge(self, source: int, target: int, kind: str = "flow", label: str = "") -> None:
        self.edges.append([source, target, str(kind)[:12], str(label)[:80]])
        self._commit()

    def update_node(self, idx: int, state: str | None = None, detail: str | None = None) -> None:
        if 0 <= idx < len(self.nodes):
            if state is not None:
                self.nodes[idx]["s"] = state
            if detail is not None:
                self.nodes[idx]["d"] = str(detail)[:1200]
            self.nodes[idx]["b"] = self._rel()
            self._commit()

    def finish(self, answer: str = "", agent: str = "", state: str = "done") -> None:
        self.state = state
        self.answer = answer[:800]
        if agent:
            self.agent = agent[:80]
        rel = self._rel()
        for n in self.nodes:
            if n["s"] == "running":
                n["s"] = "ok" if state == "done" else "fail"
                n["b"] = rel
        self._commit()

    def fail(self, error: str = "") -> None:
        self.finish(answer=error, state="failed")


class JourneyStore:
    """Percorsi completi delle ultime domande, ricostruiti in tempo reale dalla A alla Z."""

    def __init__(self) -> None:
        self._items: OrderedDict[str, dict] = OrderedDict()
        self.seq = 0

    def start_journey(self, query: str, who: str = "utente") -> JourneyTracker:
        key = uuid.uuid4().hex[:12]
        return JourneyTracker(self, key, query, who)

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
