import time

import customtkinter as ctk

from ui import theme
from ui.orb import STATE_COLOR

WIDTH, HEIGHT = 400, 540
IDLE_HIDE_SECONDS = 45
STATE_TEXT = {"idle": "Pronta · di' «Atena» o premi {hotkey}", "listening": "Ti ascolto…", "thinking": "Ci penso…",
              "speaking": "Sto parlando · Esc per interrompere", "offline": "ATENA non raggiungibile · riprovo…",
              "error": "Qualcosa non va", "alert": "Attenzione: controlla i messaggi"}
SHORTCUTS = (("🖥 Schermo", "Guarda il mio schermo e dimmi cosa vedi"),
             ("✍ Scrivi", "Aiutami a migliorare il testo che sto scrivendo"),
             ("📷 Guardami", "Guardami dalla webcam"))
WELCOME = ("Ciao! Sono ATENA. Posso creare cartelle e file, aprire documenti e programmi, aiutarti a scrivere e guardare "
           "lo schermo o la webcam quando me lo chiedi. Quello che posso fare lo decidi tu in Impostazioni → Permessi.")


def _icon_button(parent, text: str, command):
    return ctk.CTkButton(parent, text=text, width=28, height=28, fg_color="transparent", hover_color=theme.LINE,
                         text_color=theme.DIM, command=command)


class Panel:
    def __init__(self, root, scale: float, hotkey: str, actions: dict) -> None:
        self.root, self.scale, self.hotkey, self.actions = root, scale, hotkey, actions
        self.last_activity = time.time()
        self.window = ctk.CTkToplevel(root, fg_color=theme.PANEL)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.geometry(f"{WIDTH}x{HEIGHT}")
        self.window.withdraw()
        self.window.after(50, lambda: theme.round_corners(self.window))
        self._header()
        self.feed = ctk.CTkScrollableFrame(self.window, fg_color=theme.BG, corner_radius=12)
        self.feed.pack(fill="both", expand=True, padx=12)
        self.bubble("atena", WELCOME)
        self._shortcuts()
        self._input()

    def _header(self) -> None:
        head = ctk.CTkFrame(self.window, fg_color=theme.PANEL, corner_radius=0)
        head.pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(head, text="ATENA", font=(theme.FONT, 15, "bold"), text_color=theme.TEXT).pack(side="left")
        _icon_button(head, "✕", self.hide).pack(side="right")
        _icon_button(head, "⚙", self.actions["settings"]).pack(side="right")
        _icon_button(head, "🛡", self.actions["permissions"]).pack(side="right")
        self.status = ctk.CTkLabel(self.window, text="", font=(theme.FONT, 12), text_color=theme.DIM, anchor="w")
        self.status.pack(fill="x", padx=16, pady=(0, 8))

    def _shortcuts(self) -> None:
        row = ctk.CTkFrame(self.window, fg_color=theme.PANEL)
        row.pack(fill="x", padx=12, pady=(8, 0))
        for label, prompt in SHORTCUTS:
            ctk.CTkButton(row, text=label, height=26, corner_radius=13, fg_color=theme.CARD, hover_color=theme.LINE,
                          text_color=theme.TEXT, font=(theme.FONT, 12), width=10,
                          command=lambda text=prompt: self.actions["ask"](text)).pack(side="left", padx=(0, 6))

    def _input(self) -> None:
        row = ctk.CTkFrame(self.window, fg_color=theme.PANEL)
        row.pack(fill="x", padx=12, pady=12)
        self.entry = ctk.CTkEntry(row, placeholder_text="Scrivi ad ATENA…", height=38, corner_radius=19,
                                  fg_color=theme.CARD, border_color=theme.LINE, text_color=theme.TEXT, font=(theme.FONT, 13))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self._send)
        self.entry.bind("<Escape>", lambda _e: self.actions["stop"]())
        ctk.CTkButton(row, text="🎙", width=38, height=38, corner_radius=19, fg_color=theme.CARD, hover_color=theme.LINE,
                      command=self.actions["listen"]).pack(side="left", padx=(6, 0))
        ctk.CTkButton(row, text="➤", width=38, height=38, corner_radius=19, fg_color=theme.BLUE, hover_color=theme.BLUE_HOVER,
                      command=self._send).pack(side="left", padx=(6, 0))

    def _send(self, *_args) -> None:
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.actions["ask"](text)

    @property
    def visible(self) -> bool:
        return bool(self.window.winfo_viewable())

    def has_focus(self) -> bool:
        focused = self.root.focus_get()
        return bool(focused and str(focused).startswith(str(self.window)))

    def place(self, orb_x: int, orb_y: int, orb_size: int) -> None:
        left, top, right, bottom = theme.work_area()
        w, h, gap = int(WIDTH * self.scale), int(HEIGHT * self.scale), int(8 * self.scale)
        x = min(max(left + gap, orb_x + orb_size - w), right - w - gap)
        y = orb_y - h - gap if orb_y - h - gap > top + gap else min(orb_y + orb_size + gap, bottom - h - gap)
        self.window.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def show(self, focus: bool = False) -> None:
        self.window.deiconify()
        self.window.lift()
        self.last_activity = time.time()
        if focus:
            self.window.after(80, lambda: (self.window.focus_force(), self.entry.focus_set()))

    def hide(self) -> None:
        self.window.withdraw()

    def idle_too_long(self) -> bool:
        return self.visible and time.time() - self.last_activity > IDLE_HIDE_SECONDS and not self.has_focus()

    def set_state(self, state: str) -> None:
        self.last_activity = time.time()
        color = theme.DIM if state == "idle" else STATE_COLOR.get(state, theme.DIM)
        self.status.configure(text=STATE_TEXT.get(state, "").format(hotkey=self.hotkey.upper()), text_color=color)

    def bubble(self, who: str, text: str, long: str = "") -> None:
        mine = who == "user"
        wrap = ctk.CTkFrame(self.feed, fg_color="transparent")
        wrap.pack(fill="x", pady=4, padx=4)
        card = ctk.CTkFrame(wrap, fg_color="#1b3a5c" if mine else theme.CARD, corner_radius=12)
        card.pack(anchor="e" if mine else "w", padx=(40, 0) if mine else (0, 40))
        if text:
            ctk.CTkLabel(card, text=text, wraplength=270, justify="left", font=(theme.FONT, 13), text_color=theme.TEXT
                         ).pack(padx=12, pady=8, anchor="w")
        if long:
            box = ctk.CTkTextbox(card, width=300, height=min(260, 22 + 17 * long.count("\n") + len(long) // 3),
                                 fg_color=theme.BG, text_color=theme.TEXT, font=(theme.MONO, 11), wrap="word")
            box.insert("1.0", long)
            box.configure(state="disabled")
            box.pack(padx=10, pady=(0 if text else 10, 6))
            ctk.CTkButton(card, text="Copia", height=24, width=70, fg_color=theme.LINE, hover_color="#2d4268",
                          font=(theme.FONT, 11), command=lambda: self._copy(long)).pack(padx=10, pady=(0, 8), anchor="e")
        self.last_activity = time.time()
        self._scroll_end()

    def note(self, text: str, color: str = theme.DIM) -> None:
        ctk.CTkLabel(self.feed, text=text, font=(theme.FONT, 11), text_color=color, wraplength=330, justify="left"
                     ).pack(anchor="w", padx=10, pady=1)
        self._scroll_end()

    def _scroll_end(self) -> None:
        self.root.after(60, lambda: self.feed._parent_canvas.yview_moveto(1.0))

    def _copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
