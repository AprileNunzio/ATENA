import time

import keyboard
import pyperclip

from actions.common import Outcome, Request
from permissions.gate import Gate
from senses.windows import Focus


class Writer:
    def __init__(self, gate: Gate, focus: Focus) -> None:
        self.gate, self.focus = gate, focus

    def copy_text(self, a: dict) -> Outcome:
        text = a.get("text", "")
        self.gate.check(Request("input.clipboard", "Copiare testo negli appunti", text[:1500]))
        pyperclip.copy(text)
        return Outcome("📋 Copiato negli appunti")

    def type_text(self, a: dict) -> Outcome:
        text = a.get("text", "")
        if not text:
            return Outcome("")
        window = self.focus.current()
        where = window.app if window else "finestra attiva"
        self.gate.check(Request("input.type", f"Scrivere in {where}", text[:1500]))
        previous = pyperclip.paste()
        pyperclip.copy(text)
        if not self.focus.bring_back():
            return Outcome("📋 Non trovo la finestra in cui scrivere: il testo è negli appunti, incollalo con Ctrl+V")
        keyboard.send("ctrl+v")
        time.sleep(0.4)
        pyperclip.copy(previous)
        return Outcome(f"⌨ Testo inserito in {where}")
