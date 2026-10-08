import threading
import tkinter as tk

import customtkinter as ctk

from connection import tls
from ui import theme

GUIDE = ("1. Nel pannello di ATENA apri Funzionalità → Nodi e server e premi «+ Aggiungi un nodo»: compare un codice di "
         "6 cifre e l'impronta del certificato.\n2. Scrivi qui l'indirizzo di ATENA e premi «Verifica»: confronta l'impronta "
         "che compare qui con quella del pannello. Devono essere identiche.\n3. Scrivi il codice e premi «Collega».")


class PairingWindow:
    def __init__(self, cfg: dict, verify, pair) -> None:
        self.verify, self.pair = verify, pair
        self.paired = False
        self.fingerprint = ""
        self.window = ctk.CTk(fg_color=theme.PANEL)
        self.window.title("ATENA · Collega questo PC")
        self.window.minsize(440, 600)
        self.window.geometry("500x680")
        ctk.CTkLabel(self.window, text="Collega questo PC ad ATENA", font=(theme.FONT, 20, "bold"), text_color=theme.TEXT
                     ).pack(anchor="w", padx=24, pady=(22, 6))
        ctk.CTkLabel(self.window, text=GUIDE, justify="left", wraplength=450, font=(theme.FONT, 12), text_color=theme.DIM
                     ).pack(anchor="w", padx=24)
        self.server = self._field("Indirizzo di ATENA", cfg.get("server", "").removeprefix("https://"), "es. 192.168.1.100")
        self.check = ctk.CTkButton(self.window, text="Verifica", fg_color=theme.LINE, command=self._verify)
        self.check.pack(anchor="w", padx=24, pady=(8, 0))
        self.print_label = ctk.CTkLabel(self.window, text="", font=(theme.MONO, 15, "bold"), text_color=theme.CYAN)
        self.print_label.pack(anchor="w", padx=24, pady=(6, 0))
        self.matches = tk.BooleanVar(value=False)
        self.match_box = ctk.CTkCheckBox(self.window, text="L'impronta coincide con quella del pannello di ATENA",
                                         variable=self.matches, text_color=theme.TEXT, fg_color=theme.CYAN,
                                         command=self._refresh, state="disabled")
        self.match_box.pack(anchor="w", padx=24, pady=(6, 0))
        self.code = self._field("Codice di abbinamento (6 cifre)", "", "es. 482913")
        self.name = self._field("Nome di questo PC", cfg.get("name", ""), "es. Studio")
        self.autostart = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.window, text="Avvia ATENA all'accensione del PC", variable=self.autostart,
                        text_color=theme.TEXT, fg_color=theme.CYAN, font=(theme.FONT, 12)).pack(anchor="w", padx=24, pady=(14, 0))
        self.status = ctk.CTkLabel(self.window, text="", font=(theme.FONT, 12), text_color=theme.RED, wraplength=450,
                                   justify="left")
        self.status.pack(anchor="w", padx=24, pady=(10, 0))
        self.button = ctk.CTkButton(self.window, text="Collega", height=42, fg_color=theme.BLUE, hover_color=theme.BLUE_HOVER,
                                    font=(theme.FONT, 14, "bold"), command=self._pair, state="disabled")
        self.button.pack(fill="x", padx=24, pady=(14, 18))

    def _field(self, label: str, value: str, placeholder: str) -> ctk.CTkEntry:
        ctk.CTkLabel(self.window, text=label, font=(theme.FONT, 12), text_color=theme.TEXT).pack(anchor="w", padx=24, pady=(14, 2))
        entry = ctk.CTkEntry(self.window, height=38, fg_color=theme.CARD, border_color=theme.LINE, placeholder_text=placeholder,
                             font=(theme.FONT, 14))
        if value:
            entry.insert(0, value)
        entry.pack(fill="x", padx=24)
        return entry

    def _say(self, text: str, color: str = theme.RED) -> None:
        self.status.configure(text=text, text_color=color)

    def _refresh(self) -> None:
        self.button.configure(state="normal" if self.fingerprint and self.matches.get() else "disabled")

    def _background(self, work, done) -> None:
        def run():
            try:
                result = work()
            except Exception as exc:
                message = str(exc)
                self.window.after(0, lambda: (self._say(message), self.check.configure(state="normal"), self._refresh()))
                return
            self.window.after(0, lambda: done(result))

        threading.Thread(target=run, daemon=True).start()

    def _verify(self) -> None:
        self._say("Verifico il certificato di ATENA…", theme.DIM)
        self.check.configure(state="disabled")
        address = self.server.get()
        self._background(lambda: self.verify(address), self._verified)

    def _verified(self, contact: tuple[str, str]) -> None:
        fingerprint = contact[0]
        self.fingerprint = fingerprint
        self.print_label.configure(text=f"Impronta: {tls.short(fingerprint)}")
        self.match_box.configure(state="normal")
        self.check.configure(state="normal")
        self._say("Confronta l'impronta con quella mostrata nel pannello di ATENA.", theme.DIM)
        self._refresh()

    def _pair(self) -> None:
        self._say("Collegamento in corso…", theme.DIM)
        self.button.configure(state="disabled")
        values = (self.server.get(), self.code.get().strip(), self.name.get().strip(), self.autostart.get(), self.fingerprint)
        self._background(lambda: self.pair(*values), self._paired)

    def _paired(self, _result) -> None:
        self.paired = True
        self.window.destroy()

    def run(self) -> bool:
        self.window.mainloop()
        return self.paired
