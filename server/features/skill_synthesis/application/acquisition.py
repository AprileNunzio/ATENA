import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional

from server.features.skill_synthesis.application.ports import SynthesisUnavailable
from server.features.skill_synthesis.application.synthesizer import ToolSynthesizer

logger = logging.getLogger("atena.skill_synthesis.acquisition")

WINDOW_SECONDS = 3600.0
_SPEECH_LIMIT = 600


@dataclass(frozen=True)
class Acquisition:
    ok: bool
    tool_name: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    egress_hosts: tuple = ()
    attempts: int = 0
    message: str = ""

    @property
    def speech(self) -> str:
        if not self.ok:
            return f"Non avevo uno strumento adatto e non sono riuscito a costruirlo: {self.message}"
        return str(self.data.get("summary") or self.message)[:_SPEECH_LIMIT]


def _key(goal: str) -> str:
    return " ".join(goal.lower().split())[:400]


class SkillAcquisition:
    def __init__(
        self,
        synthesizer: ToolSynthesizer,
        per_hour: int = 6,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._synthesizer = synthesizer
        self._per_hour = max(0, per_hour)
        self._clock = clock
        self._started: Deque[float] = deque()
        self._inflight: Dict[str, "asyncio.Future[Acquisition]"] = {}

    async def acquire(self, goal: str, context: Optional[Dict[str, Any]] = None) -> Acquisition:
        key = _key(goal)
        if not key:
            return Acquisition(False, message="richiesta vuota")
        pending = self._inflight.get(key)
        if pending is not None:
            return await asyncio.shield(pending)
        if not self._admit():
            return Acquisition(False, message=f"limite di {self._per_hour} nuovi strumenti all'ora raggiunto")
        task = asyncio.ensure_future(self._build(goal, dict(context or {})))
        self._inflight[key] = task
        task.add_done_callback(lambda _: self._inflight.pop(key, None))
        return await asyncio.shield(task)

    def _admit(self) -> bool:
        now = self._clock()
        while self._started and now - self._started[0] >= WINDOW_SECONDS:
            self._started.popleft()
        if len(self._started) >= self._per_hour:
            return False
        self._started.append(now)
        return True

    async def _build(self, goal: str, context: Dict[str, Any]) -> Acquisition:
        try:
            outcome = await self._synthesizer.synthesize(goal, context)
        except SynthesisUnavailable as exc:
            return Acquisition(False, message=str(exc))
        if not outcome.ok or outcome.tool is None:
            logger.warning("skill acquisition failed for %r: %s", goal[:80], outcome.message)
            return Acquisition(False, attempts=outcome.attempts, message=outcome.message)
        logger.info("acquired skill %s in %d attempts", outcome.tool.name, outcome.attempts)
        return Acquisition(
            True,
            tool_name=outcome.tool.name,
            data=dict((outcome.run.data if outcome.run else None) or {}),
            source=outcome.tool.source,
            egress_hosts=tuple(outcome.tool.egress_hosts),
            attempts=outcome.attempts,
            message=outcome.message,
        )
