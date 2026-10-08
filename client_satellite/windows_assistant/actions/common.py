import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from permissions.gate import Denied, Gate, Request

TEXT_LIMIT = 20000
OUTPUT_LIMIT = 12000
EXEC_EXT = {".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".msi",
            ".msp", ".scr", ".pif", ".hta", ".cpl", ".reg", ".lnk", ".jar", ".py", ".pyw", ".appref-ms", ".url"}


DESTRUCTIVE = re.compile(
    r"remove-item|\brm\b|\brmdir\b|\brd\s+/s|\bdel\b|\berase\b|format-volume|\bformat\s+[a-z]:|clear-disk|"
    r"stop-computer|restart-computer|\bshutdown\b|set-executionpolicy|vssadmin|bcdedit|\breg\s+delete|cipher\s+/w|"
    r"invoke-expression|\biex\b|downloadstring|downloadfile|invoke-webrequest|\biwr\b|start-bitstransfer|"
    r"-encodedcommand|\bmkfs\b|\bdd\s+if=|:\(\)\s*\{|curl[^|]*\|\s*(?:ba)?sh|wget[^|]*\|\s*(?:ba)?sh",
    re.I)


def destructive(text: str) -> bool:
    return bool(DESTRUCTIVE.search(text or ""))


class ActionError(Exception):
    pass


@dataclass
class Outcome:
    line: str
    data: dict = field(default_factory=dict)


class PathGuard:
    def __init__(self, gate: Gate, roots: list[str]) -> None:
        self.gate = gate
        self.roots = list(dict.fromkeys(Path(r).resolve() for r in roots if r))

    def inside(self, path: Path) -> bool:
        return any(path == root or root in path.parents for root in self.roots)

    def resolve(self, raw: str, purpose: str) -> Path:
        if not raw or not raw.strip():
            raise ActionError("percorso mancante")
        path = Path(os.path.expandvars(os.path.expanduser(raw.strip().strip('"'))))
        if not path.is_absolute():
            path = Path.home() / "Documents" / path
        path = path.resolve()
        if not self.inside(path):
            self.gate.check(Request("files.outside", f"{purpose}: {path}", f"Percorso fuori dalle cartelle personali:\n{path}"))
        return path


def clip(text: str, limit: int = OUTPUT_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n… ({len(text) - limit} caratteri omessi)"


__all__ = ["ActionError", "Denied", "Outcome", "PathGuard", "Request", "clip", "EXEC_EXT", "TEXT_LIMIT"]
