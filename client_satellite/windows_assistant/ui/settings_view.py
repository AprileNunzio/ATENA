import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ui import theme

BACKUP_HOURS = {"Ogni ora": 1, "Ogni 6 ore": 6, "Ogni giorno": 24, "Ogni settimana": 168}


class SettingsWindow:
    def __init__(self, root, cfg: dict, autostart: bool, fingerprint: str, actions: dict) -> None:
        self.cfg, self.actions = cfg, actions
        self.window = ctk.CTkToplevel(root, fg_color=theme.PANEL)
        self.window.title("ATENA · Impostazioni")
        self.window.attributes("-topmost", True)
        self.window.minsize(440, 480)
        self.window.geometry("500x720")
        body = ctk.CTkScrollableFrame(self.window, fg_color=theme.PANEL)
        body.pack(fill="both", expand=True)
        self.body = body
        ctk.CTkLabel(body, text="Impostazioni", font=(theme.FONT, 18, "bold"), text_color=theme.TEXT
                     ).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(body, text=f"Collegata a {cfg['server']} come «{cfg['name']}»\nCertificato verificato: {fingerprint}",
                     font=(theme.FONT, 12), text_color=theme.DIM, justify="left").pack(anchor="w", padx=20, pady=(0, 12))
        self.values = {
            "voice": self._switch("Risposte a voce", "Se spento, ATENA risponde solo per iscritto nel pannello.", cfg["voice"]),
            "headset": self._switch("Uso le cuffie", "Puoi interrompere ATENA parlandole sopra.", cfg["headset"]),
            "autostart": self._switch("Avvia con Windows", "ATENA parte da sola quando accendi il PC.", autostart),
        }
        self.hotkey = self._entry("Tasti rapidi per parlare", cfg["hotkey"])
        self._backup()
        row = ctk.CTkFrame(body, fg_color=theme.PANEL)
        row.pack(fill="x", padx=16, pady=14)
        ctk.CTkButton(row, text="Salva", fg_color=theme.BLUE, hover_color=theme.BLUE_HOVER, command=self._save).pack(side="right")
        ctk.CTkButton(row, text="🛡 Permessi…", fg_color=theme.LINE, command=actions["permissions"]).pack(side="right", padx=8)
        ctk.CTkButton(row, text="Scollega questo PC", fg_color="transparent", border_width=1, border_color=theme.RED,
                      text_color=theme.RED, hover_color="#3a1d27",
                      command=lambda: (self.window.destroy(), actions["unpair"]())).pack(side="left")

    def _card(self) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self.body, fg_color=theme.CARD, corner_radius=10)
        card.pack(fill="x", padx=16, pady=4)
        return card

    def _switch(self, title: str, hint: str, value: bool) -> tk.BooleanVar:
        card, var = self._card(), tk.BooleanVar(value=bool(value))
        ctk.CTkSwitch(card, text=title, variable=var, font=(theme.FONT, 13), text_color=theme.TEXT,
                      progress_color=theme.CYAN).pack(anchor="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(card, text=hint, font=(theme.FONT, 11), text_color=theme.DIM, wraplength=420, justify="left"
                     ).pack(anchor="w", padx=12, pady=(2, 10))
        return var

    def _entry(self, title: str, value: str) -> ctk.CTkEntry:
        card = self._card()
        ctk.CTkLabel(card, text=title, font=(theme.FONT, 13), text_color=theme.TEXT).pack(anchor="w", padx=12, pady=(10, 2))
        entry = ctk.CTkEntry(card, fg_color=theme.BG, border_color=theme.LINE)
        entry.insert(0, value)
        entry.pack(fill="x", padx=12, pady=(0, 10))
        return entry

    def _backup(self) -> None:
        card = self._card()
        ctk.CTkLabel(card, text="Backup automatico delle cartelle", font=(theme.FONT, 13), text_color=theme.TEXT
                     ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(card, text="ATENA copia le cartelle scelte in un archivio .zip nella destinazione (disco esterno o NAS) "
                     "e tiene le ultime 10 copie. Ogni file modificato da ATENA ha comunque una copia di sicurezza.",
                     font=(theme.FONT, 11), text_color=theme.DIM, wraplength=420, justify="left").pack(anchor="w", padx=12)
        self.sources = list(self.cfg.get("backup_folders") or [])
        self.target = tk.StringVar(value=self.cfg.get("backup_target") or "")
        self.source_label = ctk.CTkLabel(card, text="", font=(theme.FONT, 11), text_color=theme.TEXT, justify="left",
                                         wraplength=420)
        self.source_label.pack(anchor="w", padx=12, pady=(6, 2))
        self.target_label = ctk.CTkLabel(card, text="", font=(theme.FONT, 11), text_color=theme.TEXT, wraplength=420)
        self.target_label.pack(anchor="w", padx=12)
        self._draw_backup()
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)
        ctk.CTkButton(row, text="+ Cartella", width=90, fg_color=theme.LINE, command=self._add_source).pack(side="left")
        ctk.CTkButton(row, text="Svuota", width=70, fg_color=theme.LINE, command=self._clear_sources).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Destinazione…", width=110, fg_color=theme.LINE, command=self._pick_target).pack(side="left")
        hours = int(self.cfg.get("backup_hours") or 24)
        self.every = ctk.CTkSegmentedButton(card, values=list(BACKUP_HOURS), selected_color=theme.BLUE)
        self.every.set(next((k for k, v in BACKUP_HOURS.items() if v == hours), "Ogni giorno"))
        self.every.pack(anchor="w", padx=12, pady=(0, 10))

    def _draw_backup(self) -> None:
        self.source_label.configure(text="Cartelle: " + ("; ".join(self.sources) if self.sources else "nessuna"))
        self.target_label.configure(text="Destinazione: " + (self.target.get() or "non scelta"))

    def _add_source(self) -> None:
        chosen = filedialog.askdirectory(parent=self.window, title="Cartella da salvare")
        if chosen and chosen not in self.sources:
            self.sources.append(chosen)
            self._draw_backup()

    def _clear_sources(self) -> None:
        self.sources = []
        self._draw_backup()

    def _pick_target(self) -> None:
        chosen = filedialog.askdirectory(parent=self.window, title="Dove salvare i backup")
        if chosen:
            self.target.set(chosen)
            self._draw_backup()

    def _save(self) -> None:
        self.cfg.update(voice=self.values["voice"].get(), headset=self.values["headset"].get(),
                        hotkey=self.hotkey.get().strip().lower() or "ctrl+alt+space",
                        backup_folders=self.sources, backup_target=self.target.get(),
                        backup_hours=BACKUP_HOURS[self.every.get()])
        self.actions["saved"](self.values["autostart"].get())
        self.window.destroy()
