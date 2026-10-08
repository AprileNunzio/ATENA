from tkinter import filedialog, messagebox

import customtkinter as ctk

from permissions.catalog import CAPABILITIES, GROUPS, LEVEL_LABELS
from permissions.policy import Policy
from ui import theme

LABEL_TO_LEVEL = {label: level for level, label in LEVEL_LABELS.items()}


class PermissionsWindow:
    def __init__(self, root, policy: Policy, on_change) -> None:
        self.policy, self.on_change = policy, on_change
        self.window = ctk.CTkToplevel(root, fg_color=theme.PANEL)
        self.window.title("ATENA · Permessi")
        self.window.attributes("-topmost", True)
        self.window.minsize(460, 420)
        self.window.geometry("640x720")
        ctk.CTkLabel(self.window, text="Cosa può fare ATENA su questo PC", font=(theme.FONT, 18, "bold"),
                     text_color=theme.TEXT).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(self.window, text="«Chiedi ogni volta» mostra sempre l'azione esatta prima di eseguirla.",
                     font=(theme.FONT, 12), text_color=theme.DIM).pack(anchor="w", padx=20, pady=(0, 8))
        if policy.tampered:
            ctk.CTkLabel(self.window, text="⚠ Il file dei permessi era stato modificato fuori da ATENA: ho ripristinato i "
                         "valori sicuri.", text_color=theme.AMBER, wraplength=580, justify="left").pack(anchor="w", padx=20)
        self.body = ctk.CTkScrollableFrame(self.window, fg_color=theme.BG, corner_radius=12)
        self.body.pack(fill="both", expand=True, padx=16, pady=(4, 16))
        for group in GROUPS:
            self._group(group)
        self._folders()

    def _group(self, group: str) -> None:
        ctk.CTkLabel(self.body, text=group.upper(), font=(theme.FONT, 11, "bold"), text_color=theme.CYAN
                     ).pack(anchor="w", padx=8, pady=(14, 4))
        for capability in (c for c in CAPABILITIES if c.group == group):
            card = ctk.CTkFrame(self.body, fg_color=theme.CARD, corner_radius=10)
            card.pack(fill="x", padx=4, pady=3)
            title = f"⚠ {capability.title}" if capability.risky else capability.title
            ctk.CTkLabel(card, text=title, font=(theme.FONT, 13), text_color=theme.AMBER if capability.risky else theme.TEXT,
                         anchor="w").pack(fill="x", padx=12, pady=(8, 0))
            ctk.CTkLabel(card, text=capability.hint, font=(theme.FONT, 11), text_color=theme.DIM, wraplength=540,
                         justify="left", anchor="w").pack(fill="x", padx=12)
            switch = ctk.CTkSegmentedButton(card, values=list(LEVEL_LABELS.values()), selected_color=theme.BLUE,
                                            command=lambda label, key=capability.key: self._set(key, label))
            switch.set(LEVEL_LABELS[self.policy.level(capability.key)])
            switch.pack(anchor="w", padx=12, pady=(6, 10))

    def _set(self, key: str, label: str) -> None:
        self.policy.set(key, LABEL_TO_LEVEL[label])
        self.on_change(key, LABEL_TO_LEVEL[label])

    def _folders(self) -> None:
        ctk.CTkLabel(self.body, text="CARTELLE CONSENTITE OLTRE A QUELLE PERSONALI", font=(theme.FONT, 11, "bold"),
                     text_color=theme.CYAN).pack(anchor="w", padx=8, pady=(18, 4))
        self.folder_box = ctk.CTkFrame(self.body, fg_color=theme.CARD, corner_radius=10)
        self.folder_box.pack(fill="x", padx=4, pady=3)
        self._draw_folders()

    def _draw_folders(self) -> None:
        for child in self.folder_box.winfo_children():
            child.destroy()
        for folder in self.policy.folders:
            row = ctk.CTkFrame(self.folder_box, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)
            ctk.CTkLabel(row, text=folder, text_color=theme.TEXT, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="Rimuovi", width=70, height=24, fg_color="transparent", border_width=1,
                          border_color=theme.RED, text_color=theme.RED, command=lambda f=folder: self._remove(f)).pack(side="right")
        ctk.CTkButton(self.folder_box, text="+ Aggiungi cartella", height=28, fg_color=theme.LINE,
                      command=self._add).pack(anchor="w", padx=8, pady=8)

    def _add(self) -> None:
        chosen = filedialog.askdirectory(parent=self.window, title="Cartella in cui ATENA può lavorare")
        if not chosen:
            return
        try:
            self.policy.set_folders([*self.policy.folders, chosen])
        except ValueError as exc:
            messagebox.showerror("ATENA", str(exc), parent=self.window)
            return
        self.on_change("folders", None)
        self._draw_folders()

    def _remove(self, folder: str) -> None:
        self.policy.set_folders([f for f in self.policy.folders if f != folder])
        self.on_change("folders", None)
        self._draw_folders()

