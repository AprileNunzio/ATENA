import time
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass

QUIET_SECONDS = 0.05


@dataclass(frozen=True)
class Scope:
    tracker: object
    parent: int | None


class Probe:
    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        self.skipped = False

    def note(self, detail: str) -> None:
        self.detail = detail

    def skip(self, detail: str = "") -> None:
        self.skipped = True
        if detail:
            self.detail = detail


_scope: ContextVar[Scope | None] = ContextVar("journey_scope", default=None)


def bind(tracker, parent: int | None) -> Token:
    return _scope.set(Scope(tracker, parent))


def release(token: Token) -> None:
    _scope.reset(token)


def current() -> Scope | None:
    return _scope.get()


@asynccontextmanager
async def stage(kind: str, name: str, detail: str = "", label: str = ""):
    scope = _scope.get()
    probe = Probe(detail)
    if scope is None:
        yield probe
        return
    tracker = scope.tracker
    idx = tracker.add_node(kind, name, detail, state="running", parent=scope.parent)
    if scope.parent is not None:
        tracker.add_edge(scope.parent, idx, "flow", label)
    token = _scope.set(Scope(tracker, idx))
    try:
        yield probe
    except BaseException as exc:
        tracker.update_node(idx, state="fail", detail=f"{probe.detail}\n{type(exc).__name__}: {exc}".strip())
        raise
    finally:
        _scope.reset(token)
    tracker.update_node(idx, state="skip" if probe.skipped else "ok", detail=probe.detail)


@asynccontextmanager
async def attempt(kind: str, name: str, misses: tuple[type[BaseException], ...] = (), label: str = ""):
    scope = _scope.get()
    probe = Probe()
    if scope is None:
        yield probe
        return
    started = time.time()
    state = "ok"
    try:
        yield probe
    except misses:
        probe.skipped = True
        raise
    except BaseException as exc:
        state = "fail"
        probe.note(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        elapsed = time.time() - started
        if probe.skipped and state == "ok":
            state = "skip"
        if state != "skip" or elapsed >= QUIET_SECONDS:
            detail = probe.detail or (f"Non pertinente ({elapsed * 1000:.0f} ms)" if state == "skip" else "")
            idx = scope.tracker.add_span(kind, name, detail, state, scope.parent, started)
            if scope.parent is not None:
                scope.tracker.add_edge(scope.parent, idx, "call" if state == "ok" else "fallback", label)
