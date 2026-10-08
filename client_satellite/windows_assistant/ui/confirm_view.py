import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from permissions.catalog import Capability
from permissions.gate import Answer, Request
from ui import theme

TIMEOUT_MS = 120_000


class ConfirmDialog:
    def __init__(self, root, capability: Capability, request: Request) -> None:
        self.result = Answer(False)
        self.window = ctk.CTkToplevel(root, fg_color=theme.PANEL)
        self.window.title("ATENA · Autorizzazione richiesta")
        self.window.attributes("-topmost", True)
        self.window.minsize(420, 320)
        self.window.geometry("520x440")
        self.window.protocol("WM_DELETE_WINDOW", self._deny)
        self.capability = capability
        self._build(capability, request)
        self.window.after(TIMEOUT_MS, self._deny)
        self.window.grab_set()
        self.window.focus_force()

    def _build(self, capability: Capability, request: Request) -> None:
        w = self.window
        ctk.CTkLabel(w, text="ATENA chiede il permesso", font=(theme.FONT, 18, "bold"), text_color=theme.TEXT
                     ).pack(anchor="w", padx=20, pady=(18, 2))
        color = theme.AMBER if capability.risky else theme.CYAN
        ctk.CTkLabel(w, text=f"{'⚠ ' if capability.risky else ''}{capability.title}", font=(theme.FONT, 13, "bold"),
                     text_color=color).pack(anchor="w", padx=20)
        ctk.CTkLabel(w, text=request.summary, font=(theme.FONT, 13), text_color=theme.TEXT, wraplength=470, justify="left"
                     ).pack(anchor="w", padx=20, pady=(6, 8))
        if request.detail:
            box = ctk.CTkTextbox(w, fg_color=theme.BG, text_color=theme.TEXT, font=(theme.MONO, 11), wrap="word")
            box.insert("1.0", request.detail)
            box.configure(state="disabled")
            box.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        self.remember = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(w, text="Consenti sempre, senza chiedere più", variable=self.remember, text_color=theme.DIM,
                        fg_color=theme.CYAN, font=(theme.FONT, 12)).pack(anchor="w", padx=20, pady=(0, 6))
        row = ctk.CTkFrame(w, fg_color=theme.PANEL)
        row.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(row, text="Consenti", fg_color=theme.BLUE, hover_color=theme.BLUE_HOVER, command=self._allow
                      ).pack(side="right")
        ctk.CTkButton(row, text="Nega", fg_color="transparent", border_width=1, border_color=theme.RED,
                      text_color=theme.RED, hover_color="#3a1d27", command=self._deny).pack(side="right", padx=(0, 8))

    def _allow(self) -> None:
        remember = self.remember.get()
        if remember and self.capability.risky:
            remember = messagebox.askyesno(
                "ATENA", f"«{self.capability.title}» è un'azione delicata. Vuoi davvero che ATENA la esegua sempre senza chiedere?",
                parent=self.window)
        self._close(Answer(True, remember))

    def _deny(self) -> None:
        self._close(Answer(False))

    def _close(self, answer: Answer) -> None:
        if not self.window.winfo_exists():
            return
        self.result = answer
        self.window.grab_release()
        self.window.destroy()


def ask(root, capability: Capability, request: Request) -> Answer:
    dialog = ConfirmDialog(root, capability, request)
    root.wait_window(dialog.window)
    return dialog.result
