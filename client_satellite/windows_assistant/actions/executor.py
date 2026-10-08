import logging

from actions.common import ActionError, Outcome, PathGuard
from actions.desktop import Desktop
from actions.files import Files
from actions.launch import Launcher
from actions.remote import Remote
from actions.shell import Shell
from actions.writing import Writer
from backup.snapshots import Snapshots
from permissions.gate import Denied, Gate
from senses.windows import Focus

log = logging.getLogger("atena.actions")


class Executor:
    def __init__(self, gate: Gate, roots: list[str], focus: Focus, apps: dict[str, str], snapshots: Snapshots) -> None:
        guard = PathGuard(gate, roots)
        files, launcher = Files(gate, guard, snapshots), Launcher(gate, guard, apps)
        writer, shell, remote, desktop = Writer(gate, focus), Shell(gate, guard), Remote(gate), Desktop(gate)
        self.handlers = {
            "create_folder": files.create_folder, "create_file": files.create_file, "append_file": files.append_file,
            "read_file": files.read_file, "list_folder": files.list_folder, "search_files": files.search_files,
            "open": launcher.open, "open_app": launcher.open_app, "open_url": launcher.open_url,
            "type_text": writer.type_text, "copy_text": writer.copy_text,
            "run_powershell": shell.run_powershell, "run_script": shell.run_script, "ssh": remote.ssh,
            "window": desktop.window, "show_desktop": desktop.show_desktop, "press_keys": desktop.press_keys,
        }
        self.launcher = launcher

    def run(self, actions: list[dict]) -> tuple[list[str], list[dict]]:
        lines, results = [], []
        for action in actions:
            kind = str(action.get("type", ""))
            handler = self.handlers.get(kind)
            if handler is None:
                log.warning("Azione sconosciuta ignorata: %s", kind)
                results.append({"type": kind, "ok": False, "error": "azione sconosciuta"})
                continue
            try:
                outcome: Outcome = handler(action)
            except Denied as exc:
                lines.append(f"🛑 Non autorizzato: {exc}")
                results.append({"type": kind, "ok": False, "error": f"non autorizzato: {exc}"})
            except (ActionError, OSError) as exc:
                lines.append(f"⚠ Non fatto: {exc}")
                results.append({"type": kind, "ok": False, "error": str(exc)[:300]})
            else:
                if outcome.line:
                    lines.append(outcome.line)
                results.append({"type": kind, "ok": True, **outcome.data})
        return lines, results
