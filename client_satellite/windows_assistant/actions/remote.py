import re
import shutil
import subprocess
from pathlib import Path

from actions.common import ActionError, Outcome, Request, clip, destructive
from permissions.gate import Gate

TIMEOUT = 120
NO_WINDOW = 0x08000000
HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
USER_RE = re.compile(r"[a-z_][a-z0-9_.-]{0,31}", re.I)
OPTIONS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "-o", "LogLevel=ERROR"]


def _target(a: dict) -> tuple[str, str, int]:
    host, user = str(a.get("host", "")).strip(), str(a.get("user", "")).strip()
    if not HOST_RE.fullmatch(host):
        raise ActionError("nome o indirizzo del computer non valido")
    if not USER_RE.fullmatch(user):
        raise ActionError("nome utente SSH non valido")
    try:
        port = int(a.get("port") or 22)
    except (TypeError, ValueError) as exc:
        raise ActionError("porta SSH non valida") from exc
    if not 1 <= port <= 65535:
        raise ActionError("porta SSH non valida")
    return host, user, port


class Remote:
    def __init__(self, gate: Gate) -> None:
        self.gate = gate

    def ssh(self, a: dict) -> Outcome:
        client = shutil.which("ssh")
        if not client:
            raise ActionError("il client OpenSSH di Windows non è installato (Impostazioni → App → Funzionalità facoltative)")
        host, user, port = _target(a)
        command = str(a.get("command", "")).strip()
        if not command:
            raise ActionError("comando SSH vuoto")
        self.gate.check(Request("remote.ssh", f"Eseguire un comando su {user}@{host}:{port}", command),
                        always_ask=destructive(command))
        try:
            done = subprocess.run([client, *OPTIONS, "-p", str(port), f"{user}@{host}", "--", command], cwd=str(Path.home()),
                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT,
                                  creationflags=NO_WINDOW)
        except subprocess.TimeoutExpired as exc:
            raise ActionError(f"il computer {host} non ha risposto entro {TIMEOUT} secondi") from exc
        if done.returncode == 255 and "Host key verification failed" in done.stderr:
            raise ActionError(f"{host} non è tra i computer conosciuti: collegati una volta a mano con «ssh {user}@{host}»")
        mark = "✔" if done.returncode == 0 else "⚠"
        return Outcome(f"{mark} SSH {user}@{host} (uscita {done.returncode})",
                       {"exit": done.returncode, "output": clip(done.stdout), "error": clip(done.stderr)})
