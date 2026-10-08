import re

import keyboard

from actions.common import ActionError, Outcome, Request
from permissions.gate import Gate
from senses import windows

MODIFIERS = {"ctrl", "alt", "shift", "windows"}
KEYS = {*"abcdefghijklmnopqrstuvwxyz0123456789", *(f"f{n}" for n in range(1, 13)), "enter", "esc", "tab", "space",
        "backspace", "delete", "home", "end", "page up", "page down", "up", "down", "left", "right", "print screen"}
BLOCKED = {"ctrl+alt+delete", "windows+l", "alt+f4"}
STATES = {"minimize": windows.SW_MINIMIZE, "maximize": windows.SW_MAXIMIZE, "restore": windows.SW_RESTORE}


def parse_keys(raw: str) -> str:
    combo = "+".join(part.strip().lower() for part in re.split(r"\s*\+\s*", raw.strip()) if part.strip())
    parts = combo.split("+")
    if not combo or combo in BLOCKED or parts[-1] not in KEYS or any(p not in MODIFIERS for p in parts[:-1]):
        raise ActionError(f"combinazione di tasti non consentita: {raw}")
    return combo


class Desktop:
    def __init__(self, gate: Gate) -> None:
        self.gate = gate

    def window(self, a: dict) -> Outcome:
        op, title = str(a.get("op", "")), str(a.get("title", ""))
        if op not in (*STATES, "focus"):
            raise ActionError(f"operazione sulla finestra non valida: {op}")
        target = windows.find(title)
        if not target:
            raise ActionError(f"non trovo una finestra «{title}»")
        self.gate.check(Request("desktop.control", f"Finestra «{target.title}»: {op}"))
        if op == "focus":
            windows.bring_to_front(target)
        else:
            windows.show(target, STATES[op])
        return Outcome(f"🪟 {target.title}: {op}")

    def show_desktop(self, a: dict) -> Outcome:
        self.gate.check(Request("desktop.control", "Mostrare il desktop (ridurre tutte le finestre)"))
        keyboard.send("windows+d")
        return Outcome("🖥 Desktop mostrato")

    def press_keys(self, a: dict) -> Outcome:
        combo = parse_keys(str(a.get("keys", "")))
        self.gate.check(Request("desktop.control", f"Premere {combo}", combo))
        keyboard.send(combo)
        return Outcome(f"⌨ Premuto {combo}")
