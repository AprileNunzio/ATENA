import os
import re
import time
import zipfile
from pathlib import Path

from actions.common import TEXT_LIMIT, ActionError, Outcome, PathGuard, Request
from backup.snapshots import Snapshots
from permissions.gate import Gate

SKIP_DIRS = {"appdata", "node_modules", ".git", "$recycle.bin", "__pycache__", ".venv", "venv"}
SEARCH_SECONDS = 5
SEARCH_LIMIT = 50


def _free_name(path: Path) -> Path:
    n = 2
    while (candidate := path.with_name(f"{path.stem} ({n}){path.suffix}")).exists():
        n += 1
    return candidate


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", "replace")
    return re.sub(r"<[^>]+>", "", xml.replace("</w:p>", "\n"))


class Files:
    def __init__(self, gate: Gate, guard: PathGuard, snapshots: Snapshots) -> None:
        self.gate, self.guard, self.snapshots = gate, guard, snapshots

    def create_folder(self, a: dict) -> Outcome:
        path = self.guard.resolve(a.get("path", ""), "Crea cartella")
        self.gate.check(Request("files.folders", f"Creare la cartella {path}"))
        path.mkdir(parents=True, exist_ok=True)
        return Outcome(f"📁 Cartella pronta: {path}")

    def create_file(self, a: dict) -> Outcome:
        path = self.guard.resolve(a.get("path", ""), "Crea file")
        content = a.get("content", "")
        if path.exists() and a.get("overwrite"):
            self.gate.check(Request("files.modify", f"Sostituire {path.name}", f"{path}\n\nNuovo contenuto:\n{content[:1500]}"))
            backup = self.snapshots.save(path)
            path.write_text(content, encoding="utf-8", newline="")
            return Outcome(f"📄 File sostituito: {path} (copia di sicurezza in {backup.parent})")
        self.gate.check(Request("files.create", f"Creare il file {path.name}", f"{path}\n\n{content[:1500]}"))
        if path.exists():
            path = _free_name(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
        return Outcome(f"📄 File creato: {path}")

    def append_file(self, a: dict) -> Outcome:
        path = self.guard.resolve(a.get("path", ""), "Modifica file")
        if not path.is_file():
            raise ActionError(f"il file {path} non esiste")
        content = a.get("content", "")
        self.gate.check(Request("files.modify", f"Aggiungere testo a {path.name}", f"{path}\n\nTesto da aggiungere:\n{content[:1500]}"))
        self.snapshots.save(path)
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return Outcome(f"✏ Testo aggiunto a {path.name}")

    def read_file(self, a: dict) -> Outcome:
        path = self.guard.resolve(a.get("path", ""), "Leggi file")
        self.gate.check(Request("files.read", f"Leggere {path.name}", str(path)))
        if not path.is_file():
            raise ActionError(f"{path} non è un file")
        if path.suffix.lower() == ".docx":
            text = _docx_text(path)
        else:
            raw = path.read_bytes()[: TEXT_LIMIT * 4]
            if b"\x00" in raw[:4000]:
                raise ActionError(f"{path.name} non è un file di testo")
            text = raw.decode("utf-8", "replace")
        return Outcome(f"👁 Letto {path.name}", {"path": str(path), "content": text[:TEXT_LIMIT]})

    def list_folder(self, a: dict) -> Outcome:
        path = self.guard.resolve(a.get("path", ""), "Elenca cartella")
        self.gate.check(Request("files.read", f"Guardare nella cartella {path.name}", str(path)))
        if not path.is_dir():
            raise ActionError(f"{path} non è una cartella")
        items = [c.name + ("/" if c.is_dir() else "") for c in sorted(path.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))[:200]]
        return Outcome(f"👁 Guardato in {path.name}", {"path": str(path), "items": items})

    def search_files(self, a: dict) -> Outcome:
        query = a.get("query", "").strip().lower()
        if not query:
            raise ActionError("cosa devo cercare?")
        root = self.guard.resolve(a.get("folder") or str(Path.home()), "Cerca file")
        self.gate.check(Request("files.read", f"Cercare «{query}» in {root}"))
        found, started = [], time.time()
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            found += [os.path.join(folder, name) for name in files + dirs if query in name.lower()]
            if len(found) >= SEARCH_LIMIT or time.time() - started > SEARCH_SECONDS:
                break
        return Outcome(f"🔎 Cercato «{query}»: {len(found)} risultati", {"query": query, "found": found[:SEARCH_LIMIT]})
