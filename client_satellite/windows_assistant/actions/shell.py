import base64
import re
import shutil
import subprocess
import sys
from pathlib import Path

from actions.common import ActionError, Outcome, PathGuard, Request, clip, destructive
from permissions.gate import Gate
from settings import paths

TIMEOUT = 120
NO_WINDOW = 0x08000000
CMD_UNSAFE = re.compile(r"[&|<>^%!\"]")
POWERSHELL = ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive"]


def _run(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        done = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=TIMEOUT, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise ActionError(f"tempo scaduto dopo {TIMEOUT} secondi: {exc.cmd[0]}") from exc
    except FileNotFoundError as exc:
        raise ActionError(f"programma non trovato: {argv[0]}") from exc
    return done.returncode, done.stdout, done.stderr


def _outcome(label: str, code: int, out: str, err: str) -> Outcome:
    mark = "✔" if code == 0 else "⚠"
    return Outcome(f"{mark} {label} (uscita {code})", {"exit": code, "output": clip(out), "error": clip(err)})


def _python() -> str:
    if not paths.FROZEN:
        return sys.executable
    launcher = shutil.which("py")
    if not launcher:
        raise ActionError("Python non è installato su questo PC: non posso eseguire script .py")
    return launcher


class Shell:
    def __init__(self, gate: Gate, guard: PathGuard) -> None:
        self.gate, self.guard = gate, guard

    def run_powershell(self, a: dict) -> Outcome:
        command = a.get("command", "").strip()
        if not command:
            raise ActionError("comando PowerShell vuoto")
        self.gate.check(Request("shell.powershell", "Eseguire un comando PowerShell", command), always_ask=destructive(command))
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        code, out, err = _run([*POWERSHELL, "-EncodedCommand", encoded], Path.home())
        return _outcome("PowerShell", code, out, err)

    def run_script(self, a: dict) -> Outcome:
        path = self.guard.resolve(a.get("path", ""), "Esegui script")
        if not path.is_file():
            raise ActionError(f"lo script {path} non esiste")
        suffix = path.suffix.lower()
        if suffix == ".ps1":
            argv = [*POWERSHELL, "-ExecutionPolicy", "Bypass", "-File", str(path)]
        elif suffix in (".bat", ".cmd"):
            if CMD_UNSAFE.search(str(path)):
                raise ActionError("il percorso dello script contiene caratteri non sicuri per cmd")
            argv = ["cmd.exe", "/d", "/c", str(path)]
        elif suffix == ".py":
            argv = [_python(), str(path)]
        else:
            raise ActionError(f"tipo di script non supportato: {suffix or 'senza estensione'}")
        source = path.read_text(encoding="utf-8", errors="replace")
        self.gate.check(Request("scripts.run", f"Eseguire lo script {path.name}", f"{path}\n\n{source[:2000]}"),
                        always_ask=destructive(source))
        code, out, err = _run(argv, path.parent)
        return _outcome(f"Script {path.name}", code, out, err)
