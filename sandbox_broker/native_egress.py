import json
import logging
import os
import select
import stat
import subprocess
from typing import Optional, Sequence, Tuple, Union

from sandbox_broker.egress import EgressProxy

logger = logging.getLogger("atena.sandbox_broker.egress")

DEFAULT_MAX_BYTES = 16 * 1024 * 1024
REPORT_TIMEOUT = 5.0
MAX_REPORT = 64 * 1024


def _read_report(stream, timeout: float) -> dict:
    readable, _, _ = select.select([stream], [], [], timeout)
    if not readable:
        raise OSError("native egress proxy did not answer")
    line = stream.readline(MAX_REPORT)
    if not line:
        raise OSError("native egress proxy exited")
    report = json.loads(line)
    if not isinstance(report, dict):
        raise OSError("malformed native egress report")
    if "error" in report:
        raise OSError(f"native egress proxy: {report['error']}")
    return report


def trusted_binary(path: str) -> bool:
    try:
        info = os.stat(path)
    except OSError:
        return False
    return (
        stat.S_ISREG(info.st_mode)
        and os.access(path, os.X_OK)
        and info.st_uid in (0, os.getuid())
        and not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    )


class NativeEgressProxy:
    def __init__(
        self,
        binary: str,
        bind_host: str,
        allowed: Sequence[str],
        lifetime_seconds: float,
        max_bytes: int = DEFAULT_MAX_BYTES,
        port_range: Tuple[int, int] = (0, 0),
        hooks: Optional[dict] = None,
    ) -> None:
        self.denied: list = []
        self.carried = 0
        self._stopped = False
        config = {
            "bind": bind_host,
            "ports": list(port_range),
            "allowed": [h.lower() for h in allowed],
            "lifetime_ms": max(1, int(lifetime_seconds * 1000)),
            "max_bytes": max_bytes,
        }
        if hooks is not None:
            config["hooks"] = hooks
        self._process = subprocess.Popen(
            [binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={}, close_fds=True, start_new_session=True,
        )
        try:
            self._process.stdin.write(json.dumps(config, separators=(",", ":")).encode() + b"\n")
            self._process.stdin.flush()
            ready = _read_report(self._process.stdout, REPORT_TIMEOUT)
            self._port = int(ready["port"])
        except (OSError, ValueError, KeyError, TypeError):
            self._terminate()
            raise
        self.sandbox = str(ready.get("sandbox", "none"))
        if self.sandbox != "full":
            logger.warning("native egress proxy runs with %s kernel sandbox enforcement", self.sandbox)

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> "NativeEgressProxy":
        return self

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        try:
            self._close_stdin()
            report = _read_report(self._process.stdout, REPORT_TIMEOUT)
            self.denied = [str(h) for h in report.get("denied", [])]
            self.carried = int(report.get("carried", 0))
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("native egress proxy report lost: %s", exc)
        finally:
            self._terminate()

    def _close_stdin(self) -> None:
        try:
            self._process.stdin.close()
        except OSError:
            return

    def _terminate(self) -> None:
        try:
            self._process.wait(timeout=REPORT_TIMEOUT)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._close_stdin()
        self._process.stdout.close()

    def __enter__(self) -> "NativeEgressProxy":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


AnyEgressProxy = Union[NativeEgressProxy, EgressProxy]


def native_enabled() -> bool:
    return os.environ.get("ATENA_NATIVE", "auto").strip() != "0"


def open_egress_proxy(
    binary: str, bind_host: str, allowed: Sequence[str], lifetime_seconds: float, port_range: Tuple[int, int],
) -> AnyEgressProxy:
    if native_enabled() and trusted_binary(binary):
        try:
            return NativeEgressProxy(binary, bind_host, allowed, lifetime_seconds, port_range=port_range)
        except OSError as exc:
            logger.warning("native egress proxy unavailable, using the Python proxy: %s", exc)
    return EgressProxy(bind_host, allowed, lifetime_seconds, port_range=port_range)
