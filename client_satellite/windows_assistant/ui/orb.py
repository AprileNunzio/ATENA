import math
import tkinter as tk

from ui import theme

STATE_COLOR = {"idle": "#3b6b8f", "listening": theme.CYAN, "thinking": "#a78bfa", "speaking": theme.GREEN,
               "offline": "#5a6273", "error": theme.RED, "alert": theme.AMBER}
FRAME_MS = 40


class Orb:
    def __init__(self, root, scale: float, position: tuple, on_click, on_moved, menu_items) -> None:
        self.root, self.scale, self.on_click, self.on_moved = root, scale, on_click, on_moved
        self.state, self.level, self.phase = "idle", 0.0, 0.0
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=theme.TRANSPARENT_KEY)
        self.window.attributes("-transparentcolor", theme.TRANSPARENT_KEY)
        self.size = int(64 * scale)
        self._place(position)
        self.canvas = tk.Canvas(self.window, width=self.size, height=self.size, bg=theme.TRANSPARENT_KEY,
                                highlightthickness=0, cursor="hand2")
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag_to)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._menu)
        self.menu = tk.Menu(self.window, tearoff=0, bg=theme.PANEL, fg=theme.TEXT, activebackground=theme.LINE,
                            activeforeground=theme.TEXT, bd=0)
        self.menu_items = menu_items
        self._drag = (0, 0, 0, 0, False)
        self.root.after(FRAME_MS, self._animate)

    def _place(self, position: tuple) -> None:
        left, top, right, bottom = theme.work_area()
        margin = int(20 * self.scale)
        x = position[0] if position[0] is not None else right - self.size - margin
        y = position[1] if position[1] is not None else bottom - self.size - margin
        x, y = min(max(left, int(x)), right - self.size), min(max(top, int(y)), bottom - self.size)
        self.window.geometry(f"{self.size}x{self.size}+{x}+{y}")

    @property
    def x(self) -> int:
        return self.window.winfo_x()

    @property
    def y(self) -> int:
        return self.window.winfo_y()

    def _press(self, event) -> None:
        self._drag = (event.x_root, event.y_root, self.x, self.y, False)

    def _drag_to(self, event) -> None:
        sx, sy, ox, oy, _moved = self._drag
        if abs(event.x_root - sx) + abs(event.y_root - sy) > 4:
            self._drag = (sx, sy, ox, oy, True)
            self.window.geometry(f"+{ox + event.x_root - sx}+{oy + event.y_root - sy}")
            self.on_moved(False)

    def _release(self, event) -> None:
        if self._drag[4]:
            self.on_moved(True)
        else:
            self.on_click()

    def _menu(self, event) -> None:
        self.menu.delete(0, "end")
        for item in self.menu_items():
            if item is None:
                self.menu.add_separator()
            elif isinstance(item[1], tk.BooleanVar):
                self.menu.add_checkbutton(label=item[0], variable=item[1], command=item[2])
            else:
                self.menu.add_command(label=item[0], command=item[1])
        self.menu.tk_popup(event.x_root, event.y_root)

    def _glow(self) -> float:
        if self.state == "listening":
            pulse = 0.5 + 0.5 * math.sin(self.phase * 2.2)
            return 4 + 6 * max(pulse * 0.6, min(1.0, self.level * 18))
        if self.state == "thinking":
            return 4
        if self.state == "speaking":
            return 3 + 4 * (0.5 + 0.5 * math.sin(self.phase * 4))
        return 2 + 1.5 * (0.5 + 0.5 * math.sin(self.phase * 0.7))

    def _animate(self) -> None:
        self.root.after(FRAME_MS, self._animate)
        self.phase += 0.08
        c, k, color = self.canvas, self.scale, STATE_COLOR.get(self.state, theme.CYAN)
        center = self.size / 2
        glow = self._glow()
        c.delete("all")
        for ring in range(5, 0, -1):
            r = (18 + glow * ring / 5) * k
            c.create_oval(center - r, center - r, center + r, center + r,
                          fill=theme.mix(theme.BG, color, 0.10 + 0.08 * (5 - ring)), outline="")
        r = 18 * k
        c.create_oval(center - r, center - r, center + r, center + r, fill=theme.BG, outline=color, width=2 * k)
        if self.state == "thinking":
            for dot in range(3):
                angle = self.phase * 3 + dot * 2.094
                px, py = center + 9 * k * math.cos(angle), center + 9 * k * math.sin(angle)
                c.create_oval(px - 2.5 * k, py - 2.5 * k, px + 2.5 * k, py + 2.5 * k, fill=color, outline="")
        else:
            r = (5 + (min(5.0, self.level * 90) if self.state == "listening" else 0)) * k
            c.create_oval(center - r, center - r, center + r, center + r, fill=color, outline="")
