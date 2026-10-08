import asyncio
import time
from typing import Awaitable, Callable, Tuple

from server.config.env import settings
from server.features.sandbox.application.gateway import SandboxGateway
from server.features.sandbox.domain.errors import SandboxError
from server.features.sandbox.domain.report import ExecutionReport
from server.features.sandbox.domain.spec import ResourceLimits
from server.features.sandbox.infrastructure.broker_client import BrokerClient

OUTPUT_LIMIT = 64_000
Outcome = Tuple[bool, str, str]


class SandboxRunner:
    def __init__(self, gateway: SandboxGateway, timeout_seconds: int) -> None:
        self._gateway = gateway
        self._limits = ResourceLimits(wall_seconds=timeout_seconds)
        self._last_output = ""

    async def execute_in_sandbox(self, python_code: str) -> Outcome:
        return await self._run(self._gateway.run_python, python_code)

    async def execute_command(self, command: str) -> Outcome:
        outcome = await self._run(self._gateway.run_bash, command)
        self._last_output = "\n".join(part for part in outcome[1:] if part)[-OUTPUT_LIMIT:]
        return outcome

    def last_output(self) -> str:
        return self._last_output

    async def execute_evolutionary_twins(self, code_candidates: list[str]) -> Tuple[int, bool, str, str]:
        async def run_candidate(idx: int, code: str):
            started = time.perf_counter()
            success, stdout, stderr = await self.execute_in_sandbox(code)
            return idx, success, stdout, stderr, time.perf_counter() - started

        results = await asyncio.gather(*(run_candidate(i, code) for i, code in enumerate(code_candidates)))
        winners = sorted((r for r in results if r[1]), key=lambda r: r[4])
        best = winners[0] if winners else results[0]
        return best[0], best[1], best[2], best[3]

    async def _run(self, runner: Callable[..., Awaitable[ExecutionReport]], source: str) -> Outcome:
        try:
            report = await runner(source, limits=self._limits)
        except SandboxError as exc:
            return False, "", f"sandbox error: {exc}"
        if report.timed_out:
            return False, report.stdout, f"{report.stderr}\nexecution exceeded {self._limits.wall_seconds}s".strip()
        if report.oom_killed:
            return False, report.stdout, f"{report.stderr}\nexecution exceeded memory limit".strip()
        return report.succeeded, report.stdout, report.stderr


sandbox_gateway = SandboxGateway(BrokerClient(settings.SANDBOX_SOCKET_PATH, lambda: settings.ATENA_SECRET_KEY))
sandbox_runner = SandboxRunner(sandbox_gateway, settings.CODE_SANDBOX_TIMEOUT_SECONDS)
