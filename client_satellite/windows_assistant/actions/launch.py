import ctypes
import difflib
import os
import re
import webbrowser
from pathlib import Path

from actions.common import EXEC_EXT, ActionError, Outcome, PathGuard, Request
from permissions.gate import Gate

ALIASES = {
    "vscode": "Visual Studio Code", "vs code": "Visual Studio Code", "code": "Visual Studio Code",
    "word": "Word", "excel": "Excel", "powerpoint": "PowerPoint", "outlook": "Outlook",
    "chrome": "Google Chrome", "edge": "Microsoft Edge", "firefox": "Firefox",
    "blocco note": "Blocco note", "notepad": "Blocco note", "calcolatrice": "Calcolatrice",
    "esplora file": "Esplora file", "explorer": "Esplora file",
}
BUILTIN = {"blocco note": "notepad.exe", "notepad": "notepad.exe", "calcolatrice": "calc.exe", "calculator": "calc.exe",
           "esplora file": "explorer.exe", "explorer": "explorer.exe", "paint": "mspaint.exe"}
SHELL_OK = 32


def shell_open(target: str, params: str | None = None) -> None:
    if ctypes.windll.shell32.ShellExecuteW(None, "open", target, params, None, 1) <= SHELL_OK:
        raise ActionError(f"Windows non è riuscito ad aprire {Path(target).name}")


class Launcher:
    def __init__(self, gate: Gate, guard: PathGuard, apps: dict[str, str]) -> None:
        self.gate, self.guard, self.apps = gate, guard, apps

    def find_app(self, name: str) -> tuple[str, str] | None:
        wanted = ALIASES.get(name.strip().lower(), name).lower()
        names = {n.lower(): n for n in self.apps}
        if wanted in names:
            return names[wanted], self.apps[names[wanted]]
        partial = sorted((n for n in names if wanted in n), key=len)
        close = partial or difflib.get_close_matches(wanted, names, n=1, cutoff=0.6)
        return (names[close[0]], self.apps[names[close[0]]]) if close else None

    def open(self, a: dict) -> Outcome:
        path = self.guard.resolve(a.get("path", ""), "Apri")
        if not path.exists():
            raise ActionError(f"{path} non esiste")
        if path.is_file() and path.suffix.lower() in EXEC_EXT:
            raise ActionError(f"{path.name} è un programma o uno script: per avviarlo serve l'azione «esegui script»")
        self.gate.check(Request("open.files", f"Aprire {path.name or path}", str(path)))
        os.startfile(str(path))
        return Outcome(f"↗ Aperto: {path.name or path}")

    def open_app(self, a: dict) -> Outcome:
        name = a.get("name", "").strip()
        target = str(self.guard.resolve(a["path"], "Apri con")) if a.get("path") else ""
        found = self.find_app(name)
        label = found[0] if found else name
        self.gate.check(Request("open.apps", f"Avviare {label}" + (f" con {Path(target).name}" if target else "")))
        if found:
            shell_open(found[1], f'"{target}"' if target else None)
        elif name.lower() in BUILTIN:
            shell_open(BUILTIN[name.lower()], f'"{target}"' if target else None)
        else:
            raise ActionError(f"non trovo «{name}» tra le app installate")
        return Outcome(f"🚀 Avviato {label}" + (f" con {Path(target).name}" if target else ""))

    def open_url(self, a: dict) -> Outcome:
        url = a.get("url", "").strip()
        if not re.match(r"^https?://[^\s]+$", url, re.I):
            raise ActionError("apro solo indirizzi web http o https")
        self.gate.check(Request("open.web", f"Aprire {url[:120]}"))
        webbrowser.open(url)
        return Outcome(f"🌐 Aperto {url[:80]}")
