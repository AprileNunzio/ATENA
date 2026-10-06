import itertools
import logging
import os
import re
from typing import Protocol

log = logging.getLogger("atena.bus")

MAX_SUBSCRIPTIONS = 1 << 16
TOPIC_RE = re.compile(r"[a-z0-9_-]{1,40}(\.[a-z0-9_-]{1,40}){0,7}")
PATTERN_RE = re.compile(r"([a-z0-9_-]{1,40}|\*)(\.([a-z0-9_-]{1,40}|\*)){0,7}(\.>)?|>")
ORIGIN_RE = re.compile(r"[a-z0-9_.-]{1,64}")


class Router(Protocol):
    def subscribe(self, pattern: str) -> int: ...

    def unsubscribe(self, sid: int) -> bool: ...

    def route(self, topic: str) -> list[int]: ...

    def __len__(self) -> int: ...


def py_valid_topic(topic: str) -> bool:
    return TOPIC_RE.fullmatch(topic) is not None


def py_valid_pattern(pattern: str) -> bool:
    return PATTERN_RE.fullmatch(pattern) is not None


def py_valid_origin(origin: str) -> bool:
    return ORIGIN_RE.fullmatch(origin) is not None


def _match_parts(want: list[str], have: list[str]) -> bool:
    for i, part in enumerate(want):
        if part == ">":
            return len(have) > i
        if i >= len(have) or (part != "*" and part != have[i]):
            return False
    return len(want) == len(have)


def py_matches(pattern: str, topic: str) -> bool:
    return py_valid_pattern(pattern) and py_valid_topic(topic) and _match_parts(pattern.split("."), topic.split("."))


class PyTopicRouter:
    def __init__(self) -> None:
        self._patterns: dict[int, list[str]] = {}
        self._ids = itertools.count()

    def subscribe(self, pattern: str) -> int:
        if not py_valid_pattern(pattern):
            raise ValueError("invalid topic pattern")
        if len(self._patterns) >= MAX_SUBSCRIPTIONS:
            raise RuntimeError("subscription capacity exhausted")
        sid = next(self._ids)
        self._patterns[sid] = pattern.split(".")
        return sid

    def unsubscribe(self, sid: int) -> bool:
        return self._patterns.pop(sid, None) is not None

    def route(self, topic: str) -> list[int]:
        if not py_valid_topic(topic):
            raise ValueError("invalid topic")
        have = topic.split(".")
        return [sid for sid, want in self._patterns.items() if _match_parts(want, have)]

    def __len__(self) -> int:
        return len(self._patterns)


def _load_native():
    if os.environ.get("ATENA_NATIVE", "auto").strip() == "0":
        return None
    try:
        import atena_native
    except ImportError:
        return None
    return atena_native


_native = _load_native()

ENGINE = "rust" if _native is not None else "python"

if _native is not None:
    matches = _native.matches
    valid_topic = _native.valid_topic
    valid_pattern = _native.valid_pattern
    valid_origin = _native.valid_origin
else:
    matches, valid_topic, valid_pattern, valid_origin = py_matches, py_valid_topic, py_valid_pattern, py_valid_origin


def new_router() -> Router:
    return _native.TopicRouter() if _native is not None else PyTopicRouter()


log.info("bus router engine: %s", ENGINE)
