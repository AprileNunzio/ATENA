"""Percorso completo di una domanda, ricreato da zero a ogni richiesta.

Ogni stadio per cui passa la domanda (cache, router, leggi, giuria, agenti, cicli di
ragionamento, strumenti, modelli) registra un nodo; gli archi dicono come si passa da uno
all'altro: avanti, chiamata, ripiego sul successivo oppure ritorno indietro. Il contesto
viaggia con contextvars, quindi anche le task parallele (giurati, nodi del DAG) si agganciano
al punto giusto. Tutto è best-effort: la telemetria non deve mai rompere una risposta.
"""
import asyncio
import contextvars
import logging
import time
import uuid
from collections import deque
from contextlib import contextmanager
from typing import Any, Deque, Dict, Iterator, List, Optional, Set

logger = logging.getLogger("atena.journey")

MAX_NODES = 320
MAX_DETAIL = 1200
KEEP = 20
FLUSH_DELAY = 0.2

_current: "contextvars.ContextVar[Optional[Journey]]" = contextvars.ContextVar("atena_journey", default=None)
_parent: "contextvars.ContextVar[Optional[int]]" = contextvars.ContextVar("atena_journey_parent", default=None)
_recent: "Deque[Journey]" = deque(maxlen=KEEP)
_tasks: Set[Any] = set()


def clip(text: Any, limit: int = MAX_DETAIL) -> str:
    value = " ".join(str(text if text is not None else "").split()) if limit < 200 else str(text if text is not None else "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


class Handle:
    """Riferimento a un nodo: serve per chiuderlo o per collegarlo con un ritorno."""

    __slots__ = ("_j", "id")

    def __init__(self, journey: Optional["Journey"], node_id: Optional[int]) -> None:
        self._j, self.id = journey, node_id

    def done(self, state: str = "ok", detail: Optional[str] = None) -> "Handle":
        if self._j is not None and self.id is not None:
            self._j.close(self.id, state, detail)
        return self

    def ok(self, detail: Optional[str] = None) -> "Handle":
        return self.done("ok", detail)

    def fail(self, detail: Optional[str] = None) -> "Handle":
        return self.done("fail", detail)

    def skip(self, detail: Optional[str] = None) -> "Handle":
        return self.done("skip", detail)

    def note(self, detail: str) -> "Handle":
        if self._j is not None and self.id is not None:
            self._j.nodes[self.id]["d"] = clip(detail)
            self._j.touch()
        return self

    @property
    def state(self) -> str:
        return self._j.nodes[self.id]["s"] if self._j is not None and self.id is not None else ""


class Journey:
    def __init__(self, query: str, who: str = "") -> None:
        self.id = uuid.uuid4().hex[:16]
        self.query, self.who = clip(query, 400), who
        self.t0 = time.time()
        self.state, self.answer, self.agent = "running", "", ""
        self.nodes: List[Dict[str, Any]] = []
        self.edges: List[List[Any]] = []
        self._kids: Dict[int, List[tuple]] = {}
        self._timer: Optional[asyncio.TimerHandle] = None
        self.dirty = False

    def _rel(self) -> float:
        return round(time.time() - self.t0, 3)

    def add(self, kind: str, name: str, detail: str, state: str, parent: Optional[int], parallel: bool) -> Optional[int]:
        if len(self.nodes) >= MAX_NODES:
            return None
        node_id = len(self.nodes)
        rel = self._rel()
        self.nodes.append({"i": node_id, "p": parent, "k": kind, "n": clip(name, 90), "s": state, "a": rel,
                           "b": None if state == "running" else rel, "d": clip(detail)})
        if parent is not None:
            self._link(node_id, parent, parallel)
            self._kids.setdefault(parent, []).append((node_id, parallel))
        self.touch()
        return node_id

    def _tails(self, node_id: int) -> List[int]:
        kids = self._kids.get(node_id, [])
        if not kids:
            return [node_id]
        sequential = [k for k, par in kids if not par]
        out: List[int] = self._tails(sequential[-1]) if sequential else []
        for k, par in kids:
            if par:
                out += self._tails(k)
        return list(dict.fromkeys(out))

    def _link(self, node_id: int, parent: int, parallel: bool) -> None:
        kids = self._kids.get(parent, [])
        sequential = [k for k, par in kids if not par]
        if parallel or not sequential:
            self.edges.append([parent, node_id, "call", ""])
            return
        previous = sequential[-1]
        tails = self._tails(previous) + [x for k, par in kids if par and k > previous for x in self._tails(k)]
        tails = list(dict.fromkeys(tails))
        retry = len(tails) == 1 and self.nodes[tails[0]]["s"] == "fail"
        for tail in tails:
            self.edges.append([tail, node_id, "fallback" if retry else "flow", "passa al successivo" if retry else ""])

    def close(self, node_id: int, state: str, detail: Optional[str]) -> None:
        node = self.nodes[node_id]
        node["s"], node["b"] = state, self._rel()
        if detail is not None:
            node["d"] = clip(detail)
        self.touch()

    def back(self, source: int, target: int, label: str) -> None:
        self.edges.append([source, target, "back", clip(label, 80)])
        self.touch()

    def finish(self, state: str, answer: str, agent: str) -> None:
        self.state, self.answer, self.agent = state, clip(answer, 800), agent
        for node in self.nodes:
            if node["s"] == "running":
                node["s"], node["b"] = "ok", self._rel()
        self.dirty = True
        self._fire()

    def snapshot(self) -> Dict[str, Any]:
        return {"id": self.id, "query": self.query, "who": self.who, "state": self.state, "answer": self.answer,
                "agent": self.agent, "started": self.t0, "elapsed": self._rel(), "nodes": self.nodes, "edges": self.edges}

    def touch(self) -> None:
        self.dirty = True
        if self._timer is not None:
            return
        try:
            self._timer = asyncio.get_running_loop().call_later(FLUSH_DELAY, self._fire)
        except RuntimeError:
            return

    def _fire(self) -> None:
        self._timer = None
        try:
            task = asyncio.ensure_future(self.flush())
        except RuntimeError:
            return
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)

    async def flush(self) -> None:
        if not self.dirty:
            return
        self.dirty = False
        try:
            from server.features.llm_gateway.supervisor_bridge import bridge
            await bridge.report("journey", self.id, data=self.snapshot())
        except Exception as exc:
            logger.debug("journey report dropped: %s", exc)


_NULL = Handle(None, None)


class JourneyApi:
    def begin(self, query: str, who: str = "") -> Journey:
        journey = Journey(query, who)
        journey.add("input", "Domanda", query, "ok", None, False)
        _current.set(journey)
        _parent.set(0)
        _recent.appendleft(journey)
        return journey

    @staticmethod
    def active() -> Optional[Journey]:
        return _current.get()

    def open(self, kind: str, name: str, detail: str = "", *, parallel: bool = False, state: str = "running") -> Handle:
        try:
            journey = _current.get()
            if journey is None:
                return _NULL
            node_id = journey.add(kind, name, detail, state, _parent.get(), parallel)
            return Handle(journey, node_id) if node_id is not None else _NULL
        except Exception as exc:
            logger.debug("journey.open: %s", exc)
            return _NULL

    def step(self, kind: str, name: str, detail: str = "", state: str = "ok", *, parallel: bool = False) -> Handle:
        return self.open(kind, name, detail, parallel=parallel, state=state)

    @contextmanager
    def span(self, kind: str, name: str, detail: str = "", *, parallel: bool = False) -> Iterator[Handle]:
        handle = self.open(kind, name, detail, parallel=parallel)
        token = _parent.set(handle.id) if handle.id is not None else None
        try:
            yield handle
        except BaseException as exc:
            handle.fail(f"{type(exc).__name__}: {exc}"[:300])
            raise
        else:
            if handle.state == "running":
                handle.ok()
        finally:
            if token is not None:
                _parent.reset(token)

    def back(self, source: Handle, target: Handle, label: str) -> None:
        try:
            journey = _current.get()
            if journey is not None and source.id is not None and target.id is not None:
                journey.back(source.id, target.id, label)
        except Exception as exc:
            logger.debug("journey.back: %s", exc)

    def finish(self, answer: str, status: str = "SUCCESS", agent: str = "") -> None:
        try:
            journey = _current.get()
            if journey is not None:
                journey.add("answer", "Risposta finale", answer, "ok" if status in ("SUCCESS", "STARTED_IN_BACKGROUND") else "fail", _parent.get(), False)
                journey.finish("done" if status in ("SUCCESS", "STARTED_IN_BACKGROUND") else "failed", answer, agent)
        except Exception as exc:
            logger.debug("journey.finish: %s", exc)

    def fail(self, error: str) -> None:
        try:
            journey = _current.get()
            if journey is not None:
                journey.add("error", "Errore", error, "fail", _parent.get(), False)
                journey.finish("failed", error, "")
        except Exception as exc:
            logger.debug("journey.fail: %s", exc)

    @staticmethod
    def recent() -> List[Dict[str, Any]]:
        return [j.snapshot() for j in _recent]


journey = JourneyApi()
