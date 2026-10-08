import time
import tkinter as tk

import customtkinter as ctk

from permissions.catalog import Capability
from permissions.gate import Answer, Request
from ui import confirm_view, theme
from ui.dispatcher import Dispatcher
from ui.orb import Orb
from ui.panel import Panel
from ui.permissions_view import PermissionsWindow
from ui.settings_view import SettingsWindow


class Interface:
    def __init__(self, cfg: dict, actions: dict) -> None:
        self.cfg, self.actions = cfg, actions
        self.root = ctk.CTk()
        self.root.withdraw()
        self.root.title("ATENA")
        self.scale = theme.scale_of(self.root)
        self.dispatch = Dispatcher(self.root)
        self.muted = tk.BooleanVar(value=False)
        self.orb = Orb(self.root, self.scale, (cfg.get("orb_x"), cfg.get("orb_y")), self.toggle_panel, self._orb_moved,
                       self._menu)
        self.panel = Panel(self.root, self.scale, cfg["hotkey"],
                           {"ask": actions["ask"], "listen": actions["listen"], "stop": actions["stop"],
                            "settings": self.open_settings, "permissions": self.open_permissions})
        self.root.after(1000, self._autohide)

    def _menu(self) -> list:
        self.muted.set(self.actions["is_muted"]())
        return [("Apri ATENA", self.toggle_panel), ("Parla con ATENA", self.actions["listen"]),
                ("Microfono in pausa", self.muted, lambda: self.actions["mute"](self.muted.get())), None,
                ("Permessi…", self.open_permissions), ("Impostazioni…", self.open_settings), ("Esci", self.actions["quit"])]

    def _orb_moved(self, finished: bool) -> None:
        if self.panel.visible:
            self.panel.place(self.orb.x, self.orb.y, self.orb.size)
        if finished:
            self.cfg["orb_x"], self.cfg["orb_y"] = self.orb.x, self.orb.y
            self.actions["save"]()

    def _autohide(self) -> None:
        self.root.after(1000, self._autohide)
        if self.orb.state == "idle" and self.panel.idle_too_long():
            self.panel.hide()

    def run(self) -> None:
        self.root.mainloop()

    def quit(self) -> None:
        self.root.quit()

    def set_state(self, state: str) -> None:
        self.orb.state = state
        self.panel.set_state(state)

    def set_level(self, level: float) -> None:
        self.orb.level = level

    def show_panel(self, focus: bool = False) -> None:
        self.panel.place(self.orb.x, self.orb.y, self.orb.size)
        self.panel.show(focus)

    def toggle_panel(self) -> None:
        if self.panel.visible:
            self.panel.hide()
        else:
            self.show_panel(focus=True)

    def say(self, who: str, text: str, long: str = "") -> None:
        self.panel.bubble(who, text, long)

    def note(self, text: str, color: str = theme.DIM) -> None:
        self.panel.note(text, color)

    def alert(self, text: str) -> None:
        self.show_panel()
        self.panel.note(text, theme.AMBER)
        self.set_state("alert")

    def confirm(self, capability: Capability, request: Request) -> Answer:
        self.show_panel()
        self.panel.last_activity = time.time()
        return confirm_view.ask(self.root, capability, request)

    def open_settings(self) -> None:
        SettingsWindow(self.root, self.cfg, self.actions["autostart"](), self.actions["fingerprint"](),
                       {"permissions": self.open_permissions, "unpair": self.actions["unpair"],
                        "saved": self.actions["settings_saved"]})

    def open_permissions(self) -> None:
        PermissionsWindow(self.root, self.actions["policy"](), self.actions["permissions_changed"])
