"""Esecuzione locale delle azioni decise da ATENA, con regole di sicurezza fisse:
- si scrive solo dentro la cartella utente, le cartelle note di Windows o quelle aggiunte nelle impostazioni;
- non si cancella mai nulla; un file esistente si sovrascrive solo dopo conferma;
- non si avviano mai programmi o script dai percorsi: le app si aprono solo dal menu Start."""
import ctypes
import difflib
import os
import re
import time
import webbrowser
import zipfile
from pathlib import Path

EXEC_EXT = {".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".msi",
            ".msp", ".scr", ".pif", ".hta", ".cpl", ".reg", ".lnk", ".jar", ".py", ".pyw", ".appref-ms", ".url"}
SKIP_DIRS = {"appdata", "node_modules", ".git", "$recycle.bin", "__pycache__", ".venv", "venv"}
TEXT_LIMIT = 20000
ALIASES = {
    "vscode": "Visual Studio Code", "vs code": "Visual Studio Code", "code": "Visual Studio Code",
    "word": "Word", "excel": "Excel", "powerpoint": "PowerPoint", "outlook": "Outlook",
    "chrome": "Google Chrome", "edge": "Microsoft Edge", "firefox": "Firefox",
    "blocco note": "Blocco note", "notepad": "Blocco note", "calcolatrice": "Calcolatrice",
    "esplora file": "Esplora file", "explorer": "Esplora file",
}
BUILTIN = {"blocco note": "notepad.exe", "notepad": "notepad.exe", "calcolatrice": "calc.exe", "calculator": "calc.exe",
           "esplora file": "explorer.exe", "explorer": "explorer.exe", "paint": "mspaint.exe",
           "prompt dei comandi": None, "terminale": None}


class Refused(Exception):
    pass


class Executor:
    def __init__(self, focus, apps: dict, extra_roots: list[str], confirm, notify) -> None:
        self.focus, self.apps, self.confirm, self.notify = focus, apps, confirm, notify
        # cartella utente + cartelle note (Download, Documenti… anche se spostate su altri dischi) + cartelle aggiunte
        self.roots = list(dict.fromkeys(Path(p).resolve() for p in [Path.home(), *extra_roots] if p))

    # -- percorsi -----------------------------------------------------------------------------------------------
    def _path(self, raw: str) -> Path:
        if not raw:
            raise Refused("percorso mancante")
        p = Path(os.path.expandvars(os.path.expanduser(raw.strip().strip('"'))))
        if not p.is_absolute():
            p = Path.home() / "Documents" / p
        p = p.resolve()
        if not any(p == r or r in p.parents for r in self.roots):
            raise Refused(f"per sicurezza lavoro solo nella tua cartella utente, non in {p}")
        return p

    @staticmethod
    def _free_name(p: Path) -> Path:
        n = 2
        while True:
            candidate = p.with_name(f"{p.stem} ({n}){p.suffix}")
            if not candidate.exists():
                return candidate
            n += 1

    # -- azioni -------------------------------------------------------------------------------------------------
    def run(self, actions: list[dict]) -> tuple[list[str], list[dict]]:
        done, results = [], []
        for a in actions:
            kind = a.get("type", "")
            try:
                fn = getattr(self, "do_" + kind)
            except AttributeError:
                continue
            try:
                out = fn(a)
            except Refused as exc:
                done.append(f"⚠ Non fatto: {exc}")
                results.append({"type": kind, "ok": False, "error": str(exc)})
            except Exception as exc:
                done.append(f"⚠ {kind}: {exc}")
                results.append({"type": kind, "ok": False, "error": str(exc)[:300]})
            else:
                if isinstance(out, tuple):
                    done.append(out[0])
                    results.append({"type": kind, "ok": True, **out[1]})
                elif out:
                    done.append(out)
        return done, results

    def do_create_folder(self, a):
        p = self._path(a.get("path", ""))
        p.mkdir(parents=True, exist_ok=True)
        return f"📁 Cartella pronta: {p}"

    def do_create_file(self, a):
        p = self._path(a.get("path", ""))
        if p.exists():
            if a.get("overwrite") and self.confirm(f"Il file esiste già:\n{p}\n\nVuoi che ATENA lo sostituisca?"):
                pass
            else:
                p = self._free_name(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a.get("content", ""), encoding="utf-8", newline="")
        return f"📄 File creato: {p}"

    def do_append_file(self, a):
        p = self._path(a.get("path", ""))
        if not p.exists():
            raise Refused(f"il file {p} non esiste")
        with p.open("a", encoding="utf-8", newline="") as f:
            f.write(a.get("content", ""))
        return f"✏ Testo aggiunto a {p.name}"

    def do_open(self, a):
        p = self._path(a.get("path", ""))
        if not p.exists():
            raise Refused(f"{p} non esiste")
        if p.is_file() and p.suffix.lower() in EXEC_EXT:
            ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", f'/select,"{p}"', None, 1)
            raise Refused(f"per sicurezza non avvio programmi o script ({p.name}): te l'ho mostrato nella cartella")
        os.startfile(str(p))
        return f"↗ Aperto: {p.name or p}"

    def _find_app(self, name: str) -> tuple[str, str] | None:
        key = name.strip().lower()
        wanted = ALIASES.get(key, name).lower()
        names = {n.lower(): n for n in self.apps}
        if wanted in names:
            return names[wanted], self.apps[names[wanted]]
        partial = sorted((n for n in names if wanted in n), key=len)
        if partial:
            return names[partial[0]], self.apps[names[partial[0]]]
        close = difflib.get_close_matches(wanted, names, n=1, cutoff=0.6)
        if close:
            return names[close[0]], self.apps[names[close[0]]]
        return None

    def do_open_app(self, a):
        name = a.get("name", "")
        target = ""
        if a.get("path"):
            target = str(self._path(a["path"]))
        found = self._find_app(name)
        if found:
            label, lnk = found
            params = f'"{target}"' if target else None
            if ctypes.windll.shell32.ShellExecuteW(None, "open", lnk, params, None, 1) <= 32:
                raise Refused(f"Windows non è riuscito ad avviare {label}")
            return f"🚀 Avviato {label}" + (f" con {Path(target).name}" if target else "")
        exe = BUILTIN.get(name.strip().lower())
        if exe:
            os.startfile(exe) if not target else ctypes.windll.shell32.ShellExecuteW(None, "open", exe, f'"{target}"', None, 1)
            return f"🚀 Avviato {name}"
        if name.lower() in ("visual studio code", "vscode", "code") and target:
            os.startfile(target)  # senza VS Code apre la cartella o il file
            return f"↗ VS Code non trovato: ho aperto {Path(target).name}"
        raise Refused(f"non trovo «{name}» tra le app installate")

    def do_open_url(self, a):
        url = a.get("url", "").strip()
        if not re.match(r"^https?://", url, re.I):
            raise Refused("apro solo indirizzi web http o https")
        webbrowser.open(url)
        return f"🌐 Aperto {url[:80]}"

    def do_copy_text(self, a):
        import pyperclip
        pyperclip.copy(a.get("text", ""))
        return "📋 Copiato negli appunti"

    def do_type_text(self, a):
        import keyboard
        import pyperclip
        text = a.get("text", "")
        if not text:
            return None
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None
        pyperclip.copy(text)
        if not self.focus.bring_back():
            return "📋 Non trovo la finestra in cui scrivere: il testo è negli appunti, incollalo con Ctrl+V"
        keyboard.send("ctrl+v")
        time.sleep(0.4)
        if previous is not None:
            pyperclip.copy(previous)
        w = self.focus.current()
        return f"⌨ Testo inserito in {w.app if w else 'finestra attiva'}"

    def do_read_file(self, a):
        p = self._path(a.get("path", ""))
        if not p.is_file():
            raise Refused(f"{p} non è un file")
        if p.suffix.lower() == ".docx":
            text = _docx_text(p)
        else:
            raw = p.read_bytes()[: TEXT_LIMIT * 4]
            if b"\x00" in raw[:4000]:
                raise Refused(f"{p.name} non è un file di testo")
            text = raw.decode("utf-8", "replace")
        return f"👁 Letto {p.name}", {"path": str(p), "content": text[:TEXT_LIMIT]}

    def do_list_folder(self, a):
        p = self._path(a.get("path", ""))
        if not p.is_dir():
            raise Refused(f"{p} non è una cartella")
        items = []
        for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))[:200]:
            items.append(child.name + ("/" if child.is_dir() else ""))
        return f"👁 Guardato in {p.name}", {"path": str(p), "items": items}

    def do_search_files(self, a):
        query = a.get("query", "").strip().lower()
        if not query:
            raise Refused("cosa devo cercare?")
        root = self._path(a.get("folder") or str(Path.home()))
        found, started = [], time.time()
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            for name in files + dirs:
                if query in name.lower():
                    found.append(os.path.join(dirpath, name))
            if len(found) >= 50 or time.time() - started > 5:
                break
        return f"🔎 Cercato «{query}»: {len(found)} risultati", {"query": query, "found": found[:50]}


def _docx_text(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)

