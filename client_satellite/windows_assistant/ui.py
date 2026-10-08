"""Interfaccia: una sfera discreta sempre in primo piano che si apre in un pannello di conversazione."""
import ctypes
import math
import queue
import threading
import time
import tkinter as tk

import customtkinter as ctk

ctk.set_appearance_mode("dark")

BG = "#0b1220"
PANEL = "#0f1828"
CARD = "#16223a"
LINE = "#22314f"
TEXT = "#e6edf7"
DIM = "#8a9ab5"
CYAN = "#29e0ff"
KEY = "#010203"  # colore reso trasparente attorno alla sfera
FONT = "Segoe UI"
STATE_COLOR = {"idle": "#3b6b8f", "listening": CYAN, "thinking": "#a78bfa", "speaking": "#3dffa8",
               "offline": "#5a6273", "error": "#ff6b81"}
STATE_TEXT = {"idle": "Pronta · di' «Atena» o premi {hotkey}", "listening": "Ti ascolto…", "thinking": "Ci penso…",
              "speaking": "Sto parlando · Esc per interrompere", "offline": "ATENA non raggiungibile · riprovo…",
              "error": "Qualcosa non va"}


def _round_corners(win) -> None:
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


def work_area() -> tuple[int, int, int, int]:
    """Area utile dello schermo principale in pixel reali, esclusa la barra delle applicazioni
    (winfo_screenwidth di Tk è sbagliato quando Windows usa lo zoom al 125/150%)."""
    import ctypes.wintypes as wt
    rect = wt.RECT()
    if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)


def _mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * t):02x}" for x, y in zip(a, b))


class UI:
    def __init__(self, cfg: dict, handlers: dict) -> None:
        self.cfg, self.h = cfg, handlers
        self.jobs: queue.Queue = queue.Queue()
        self.state = "idle"
        self.level = 0.0
        self.phase = 0.0
        self.last_activity = time.time()
        self.root = ctk.CTk()
        self.root.withdraw()
        self.root.title("ATENA")
        try:
            self.scale = float(self.root._get_window_scaling())  # 1.25 / 1.5 con lo zoom di Windows
        except Exception:
            self.scale = 1.0
        self.panel = None
        self._build_orb()
        self.root.after(30, self._poll)
        self.root.after(40, self._animate)

    # -- thread safety ------------------------------------------------------------------------------------------
    def post(self, fn, *args) -> None:
        self.jobs.put((fn, args))

    def call(self, fn, *args):
        """Esegue fn nel thread dell'interfaccia e ne attende il risultato (per le conferme)."""
        done, box = threading.Event(), {}

        def run():
            box["v"] = fn(*args)
            done.set()
        self.post(run)
        done.wait()
        return box.get("v")

    def _poll(self) -> None:
        while not self.jobs.empty():
            fn, args = self.jobs.get_nowait()
            try:
                fn(*args)
            except Exception as exc:  # un errore grafico non deve fermare l'assistente
                print("UI:", exc)
        if self.panel and self.panel.winfo_viewable() and self.state == "idle" and time.time() - self.last_activity > 45:
            if not self._panel_has_focus():
                self.hide_panel()
        self.root.after(30, self._poll)

    def run(self) -> None:
        self.root.mainloop()

    def quit(self) -> None:
        self.root.quit()

    # -- sfera --------------------------------------------------------------------------------------------------
    def _build_orb(self) -> None:
        self.orb = tk.Toplevel(self.root)
        self.orb.overrideredirect(True)
        self.orb.attributes("-topmost", True)
        self.orb.configure(bg=KEY)
        self.orb.attributes("-transparentcolor", KEY)
        size = self.orb_size = int(64 * self.scale)
        left, top, right, bottom = work_area()
        x = self.cfg.get("orb_x") if self.cfg.get("orb_x") is not None else right - size - int(20 * self.scale)
        y = self.cfg.get("orb_y") if self.cfg.get("orb_y") is not None else bottom - size - int(20 * self.scale)
        x, y = min(max(left, x), right - size), min(max(top, y), bottom - size)
        self.orb.geometry(f"{size}x{size}+{int(x)}+{int(y)}")
        self.canvas = tk.Canvas(self.orb, width=size, height=size, bg=KEY, highlightthickness=0, cursor="hand2")
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._orb_press)
        self.canvas.bind("<B1-Motion>", self._orb_drag)
        self.canvas.bind("<ButtonRelease-1>", self._orb_release)
        self.canvas.bind("<Button-3>", self._orb_menu)
        self.menu = tk.Menu(self.orb, tearoff=0, bg=PANEL, fg=TEXT, activebackground=LINE, activeforeground=TEXT, bd=0)
        self.menu.add_command(label="Apri ATENA", command=self.toggle_panel)
        self.menu.add_command(label="Parla con ATENA", command=lambda: self.h["listen"]())
        self.mute_var = tk.BooleanVar(value=False)
        self.menu.add_checkbutton(label="Microfono in pausa", variable=self.mute_var,
                                  command=lambda: self.h["mute"](self.mute_var.get()))
        self.menu.add_separator()
        self.menu.add_command(label="Impostazioni…", command=self.open_settings)
        self.menu.add_command(label="Esci", command=lambda: self.h["quit"]())

    def _orb_press(self, e) -> None:
        self._drag = (e.x_root, e.y_root, self.orb.winfo_x(), self.orb.winfo_y(), False)

    def _orb_drag(self, e) -> None:
        sx, sy, ox, oy, _ = self._drag
        if abs(e.x_root - sx) + abs(e.y_root - sy) > 4:
            self._drag = (sx, sy, ox, oy, True)
            self.orb.geometry(f"+{ox + e.x_root - sx}+{oy + e.y_root - sy}")
            if self.panel and self.panel.winfo_viewable():
                self._place_panel()

    def _orb_release(self, e) -> None:
        if self._drag[4]:
            self.cfg["orb_x"], self.cfg["orb_y"] = self.orb.winfo_x(), self.orb.winfo_y()
            self.h["save"]()
        else:
            self.toggle_panel()

    def _orb_menu(self, e) -> None:
        self.mute_var.set(self.h["is_muted"]())
        self.menu.tk_popup(e.x_root, e.y_root)

    def _animate(self) -> None:
        self.phase += 0.08
        c = self.canvas
        c.delete("all")
        color = STATE_COLOR.get(self.state, CYAN)
        k = self.scale
        cx = cy = self.orb_size / 2
        if self.state == "listening":
            pulse = 0.5 + 0.5 * math.sin(self.phase * 2.2)
            glow = 4 + 6 * max(pulse * 0.6, min(1.0, self.level * 18))
        elif self.state == "thinking":
            glow = 4
        elif self.state == "speaking":
            glow = 3 + 4 * (0.5 + 0.5 * math.sin(self.phase * 4))
        else:
            glow = 2 + 1.5 * (0.5 + 0.5 * math.sin(self.phase * 0.7))
        for i in range(5, 0, -1):
            r = (18 + glow * i / 5) * k
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=_mix(BG, color, 0.10 + 0.08 * (5 - i)), outline="")
        c.create_oval(cx - 18 * k, cy - 18 * k, cx + 18 * k, cy + 18 * k, fill=BG, outline=color, width=2 * k)
        if self.state == "thinking":
            for k in range(3):
                a = self.phase * 3 + k * 2.094
                px, py = cx + 9 * k * math.cos(a), cy + 9 * k * math.sin(a)
                c.create_oval(px - 2.5 * k, py - 2.5 * k, px + 2.5 * k, py + 2.5 * k, fill=color, outline="")
        else:
            r = (5 + (min(5.0, self.level * 90) if self.state == "listening" else 0)) * k
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="")
        self.root.after(40, self._animate)

    def set_state(self, state: str) -> None:
        self.state = state
        self.last_activity = time.time()
        if self.panel:
            self.status.configure(text=STATE_TEXT.get(state, "").format(hotkey=self.cfg["hotkey"].upper()),
                                  text_color=STATE_COLOR.get(state, DIM) if state != "idle" else DIM)

    # -- pannello -----------------------------------------------------------------------------------------------
    def _build_panel(self) -> None:
        p = ctk.CTkToplevel(self.root, fg_color=PANEL)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.geometry("400x540")
        self.panel = p
        p.after(50, lambda: _round_corners(p))

        head = ctk.CTkFrame(p, fg_color=PANEL, corner_radius=0)
        head.pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(head, text="ATENA", font=(FONT, 15, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkButton(head, text="✕", width=28, height=28, fg_color="transparent", hover_color=LINE, text_color=DIM,
                      command=self.hide_panel).pack(side="right")
        ctk.CTkButton(head, text="⚙", width=28, height=28, fg_color="transparent", hover_color=LINE, text_color=DIM,
                      command=self.open_settings).pack(side="right")
        self.status = ctk.CTkLabel(p, text="", font=(FONT, 12), text_color=DIM, anchor="w")
        self.status.pack(fill="x", padx=16, pady=(0, 8))

        self.feed = ctk.CTkScrollableFrame(p, fg_color=BG, corner_radius=12)
        self.feed.pack(fill="both", expand=True, padx=12)
        self._bubble("atena", "Ciao! Sono ATENA. Posso creare cartelle e file, aprire documenti e programmi, "
                              "aiutarti a scrivere e guardare lo schermo o la webcam quando me lo chiedi.")

        chips = ctk.CTkFrame(p, fg_color=PANEL)
        chips.pack(fill="x", padx=12, pady=(8, 0))
        for label, prompt in (("🖥 Schermo", "Guarda il mio schermo e dimmi cosa vedi"),
                              ("✍ Scrivi", "Aiutami a migliorare il testo che sto scrivendo"),
                              ("📷 Guardami", "Guardami dalla webcam")):
            ctk.CTkButton(chips, text=label, height=26, corner_radius=13, fg_color=CARD, hover_color=LINE,
                          text_color=TEXT, font=(FONT, 12), width=10,
                          command=lambda t=prompt: self.h["ask"](t)).pack(side="left", padx=(0, 6))

        row = ctk.CTkFrame(p, fg_color=PANEL)
        row.pack(fill="x", padx=12, pady=12)
        self.entry = ctk.CTkEntry(row, placeholder_text="Scrivi ad ATENA…", height=38, corner_radius=19,
                                  fg_color=CARD, border_color=LINE, text_color=TEXT, font=(FONT, 13))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self._send)
        self.entry.bind("<Escape>", lambda e: self.h["stop"]())
        ctk.CTkButton(row, text="🎙", width=38, height=38, corner_radius=19, fg_color=CARD, hover_color=LINE,
                      command=lambda: self.h["listen"]()).pack(side="left", padx=(6, 0))
        ctk.CTkButton(row, text="➤", width=38, height=38, corner_radius=19, fg_color="#1b8fd8", hover_color="#16c3e6",
                      command=self._send).pack(side="left", padx=(6, 0))
        self.set_state(self.state)

    def _panel_has_focus(self) -> bool:
        try:
            f = self.root.focus_get()
            return bool(f and str(f).startswith(str(self.panel)))
        except Exception:
            return False

    def _place_panel(self) -> None:
        # posizione in pixel reali, dimensioni in pixel logici (customtkinter le scala con lo zoom di Windows)
        ox, oy, o = self.orb.winfo_x(), self.orb.winfo_y(), self.orb_size
        left, top, right, bottom = work_area()
        w, h, gap = int(400 * self.scale), int(540 * self.scale), int(8 * self.scale)
        x = min(max(left + gap, ox + o - w), right - w - gap)
        y = oy - h - gap if oy - h - gap > top + gap else min(oy + o + gap, bottom - h - gap)
        self.panel.geometry(f"400x540+{x}+{y}")

    def show_panel(self, focus: bool = False) -> None:
        if not self.panel:
            self._build_panel()
        self._place_panel()
        self.panel.deiconify()
        self.panel.lift()
        self.last_activity = time.time()
        if focus:
            self.panel.after(80, lambda: (self.panel.focus_force(), self.entry.focus_set()))

    def hide_panel(self) -> None:
        if self.panel:
            self.panel.withdraw()

    def toggle_panel(self) -> None:
        if self.panel and self.panel.winfo_viewable():
            self.hide_panel()
        else:
            self.show_panel(focus=True)

    def _send(self, *_):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.h["ask"](text)

    def _bubble(self, who: str, text: str, long: str = "") -> None:
        mine = who == "user"
        wrap = ctk.CTkFrame(self.feed, fg_color="transparent")
        wrap.pack(fill="x", pady=4, padx=4)
        card = ctk.CTkFrame(wrap, fg_color="#1b3a5c" if mine else CARD, corner_radius=12)
        card.pack(anchor="e" if mine else "w", padx=(40, 0) if mine else (0, 40))
        if text:
            ctk.CTkLabel(card, text=text, wraplength=270, justify="left", font=(FONT, 13), text_color=TEXT
                         ).pack(padx=12, pady=8, anchor="w")
        if long:
            box = ctk.CTkTextbox(card, width=300, height=min(260, 22 + 17 * long.count("\n") + len(long) // 3),
                                 fg_color=BG, text_color=TEXT, font=("Cascadia Mono", 11), wrap="word")
            box.insert("1.0", long)
            box.configure(state="disabled")
            box.pack(padx=10, pady=(0 if text else 10, 6))
            ctk.CTkButton(card, text="Copia", height=24, width=70, fg_color=LINE, hover_color="#2d4268",
                          font=(FONT, 11), command=lambda: self._copy(long)).pack(padx=10, pady=(0, 8), anchor="e")
        self.root.after(60, lambda: self.feed._parent_canvas.yview_moveto(1.0))

    def _copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def say(self, who: str, text: str, long: str = "") -> None:
        if not self.panel:
            self._build_panel()
        self._bubble(who, text, long)
        self.last_activity = time.time()

    def note(self, text: str) -> None:
        if not self.panel:
            self._build_panel()
        ctk.CTkLabel(self.feed, text=text, font=(FONT, 11), text_color=DIM, wraplength=330, justify="left"
                     ).pack(anchor="w", padx=10, pady=1)
        self.root.after(60, lambda: self.feed._parent_canvas.yview_moveto(1.0))

    def confirm(self, message: str) -> bool:
        from tkinter import messagebox
        return messagebox.askyesno("ATENA", message, parent=self.panel or self.root)

    # -- impostazioni ---------------------------------------------------------------------------------------------
    def open_settings(self) -> None:
        w = ctk.CTkToplevel(self.root, fg_color=PANEL)
        w.title("ATENA · Impostazioni")
        w.geometry("440x560")
        w.attributes("-topmost", True)
        w.resizable(False, False)
        ctk.CTkLabel(w, text="Impostazioni", font=(FONT, 18, "bold"), text_color=TEXT).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(w, text=f"Collegata a {self.cfg['server']} come «{self.cfg['name']}»", font=(FONT, 12),
                     text_color=DIM).pack(anchor="w", padx=20, pady=(0, 12))
        values = {}

        def switch(key, title, hint):
            box = ctk.CTkFrame(w, fg_color=CARD, corner_radius=10)
            box.pack(fill="x", padx=16, pady=4)
            var = tk.BooleanVar(value=bool(self.cfg.get(key)) if key != "autostart" else self.h["autostart"]())
            ctk.CTkSwitch(box, text=title, variable=var, font=(FONT, 13), text_color=TEXT, progress_color=CYAN
                          ).pack(anchor="w", padx=12, pady=(10, 0))
            ctk.CTkLabel(box, text=hint, font=(FONT, 11), text_color=DIM, wraplength=370, justify="left"
                         ).pack(anchor="w", padx=12, pady=(2, 10))
            values[key] = var

        switch("wake", "Ascolto con la parola «Atena»",
               "Il microfono resta collegato ad ATENA, che si attiva solo quando sente il suo nome.")
        switch("voice", "Risposte a voce", "Se spento, ATENA risponde solo per iscritto nel pannello.")
        switch("headset", "Uso le cuffie", "Puoi interrompere ATENA parlandole sopra (senza cuffie potrebbe sentire se stessa).")
        switch("webcam", "Consenti la webcam", "La webcam si accende solo per un istante quando chiedi ad ATENA di guardarti.")
        switch("autostart", "Avvia con Windows", "ATENA parte da sola quando accendi il PC.")

        hk = ctk.CTkFrame(w, fg_color=CARD, corner_radius=10)
        hk.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(hk, text="Tasti rapidi per parlare", font=(FONT, 13), text_color=TEXT).pack(anchor="w", padx=12, pady=(10, 2))
        hotkey = ctk.CTkEntry(hk, fg_color=BG, border_color=LINE)
        hotkey.insert(0, self.cfg["hotkey"])
        hotkey.pack(fill="x", padx=12, pady=(0, 10))

        def save():
            for key, var in values.items():
                if key == "autostart":
                    self.h["set_autostart"](var.get())
                else:
                    self.cfg[key] = var.get()
            self.cfg["hotkey"] = hotkey.get().strip().lower() or "ctrl+alt+space"
            self.h["settings_changed"]()
            w.destroy()

        buttons = ctk.CTkFrame(w, fg_color=PANEL)
        buttons.pack(fill="x", padx=16, pady=14)
        ctk.CTkButton(buttons, text="Salva", fg_color="#1b8fd8", hover_color="#16c3e6", command=save).pack(side="right")
        ctk.CTkButton(buttons, text="Scollega questo PC", fg_color="transparent", border_width=1, border_color="#ff6b81",
                      text_color="#ff6b81", hover_color="#3a1d27",
                      command=lambda: (w.destroy(), self.h["unpair"]())).pack(side="left")


def pairing_window(cfg: dict, do_pair) -> bool:
    """Prima configurazione: indirizzo di ATENA + codice di abbinamento. Restituisce True se abbinato."""
    win = ctk.CTk(fg_color=PANEL)
    win.title("ATENA · Collega questo PC")
    win.geometry("480x600")
    win.resizable(False, False)
    result = {"ok": False}
    ctk.CTkLabel(win, text="Collega questo PC ad ATENA", font=(FONT, 20, "bold"), text_color=TEXT
                 ).pack(anchor="w", padx=24, pady=(22, 6))
    ctk.CTkLabel(win, justify="left", wraplength=430, font=(FONT, 12), text_color=DIM, text=(
        "1. Sul pannello di amministrazione di ATENA apri Funzionalità → Nodi e server e premi «+ Aggiungi un nodo»: "
        "comparirà un codice di 6 cifre valido per qualche minuto.\n"
        "2. Scrivi qui sotto l'indirizzo di ATENA (quello che usi nel browser, senza la porta del pannello di "
        "amministrazione, ad esempio 192.168.1.100) e il codice.")).pack(anchor="w", padx=24)

    def field(label, value="", placeholder=""):
        ctk.CTkLabel(win, text=label, font=(FONT, 12), text_color=TEXT).pack(anchor="w", padx=24, pady=(14, 2))
        e = ctk.CTkEntry(win, height=38, fg_color=CARD, border_color=LINE, placeholder_text=placeholder, font=(FONT, 14))
        if value:
            e.insert(0, value)
        e.pack(fill="x", padx=24)
        return e

    server = field("Indirizzo di ATENA", cfg.get("server", "").removeprefix("http://"), "es. 192.168.1.100")
    code = field("Codice di abbinamento (6 cifre)", "", "es. 482913")
    name = field("Nome di questo PC", cfg.get("name", ""), "es. Studio")
    auto = tk.BooleanVar(value=True)
    ctk.CTkCheckBox(win, text="Avvia ATENA all'accensione del PC", variable=auto, text_color=TEXT,
                    fg_color=CYAN, font=(FONT, 12)).pack(anchor="w", padx=24, pady=(16, 0))
    status = ctk.CTkLabel(win, text="", font=(FONT, 12), text_color="#ff6b81", wraplength=430, justify="left")
    status.pack(anchor="w", padx=24, pady=(10, 0))

    def go():
        status.configure(text="Collegamento in corso…", text_color=DIM)
        button.configure(state="disabled")

        def work():
            try:
                do_pair(server.get(), code.get().strip(), name.get().strip(), auto.get())
                result["ok"] = True
                win.after(0, win.destroy)
            except Exception as exc:
                win.after(0, lambda: (status.configure(text=str(exc), text_color="#ff6b81"),
                                      button.configure(state="normal")))
        threading.Thread(target=work, daemon=True).start()

    button = ctk.CTkButton(win, text="Collega", height=42, fg_color="#1b8fd8", hover_color="#16c3e6",
                           font=(FONT, 14, "bold"), command=go)
    button.pack(fill="x", padx=24, pady=(14, 0))
    win.bind("<Return>", lambda e: go())
    win.mainloop()
    return result["ok"]
