import ctypes
import ctypes.wintypes as wt

import customtkinter as ctk

ctk.set_appearance_mode("dark")

BG = "#0b1220"
PANEL = "#0f1828"
CARD = "#16223a"
LINE = "#22314f"
TEXT = "#e6edf7"
DIM = "#8a9ab5"
CYAN = "#29e0ff"
GREEN = "#3dffa8"
AMBER = "#ffb547"
RED = "#ff6b81"
BLUE = "#1b8fd8"
BLUE_HOVER = "#16c3e6"
TRANSPARENT_KEY = "#010203"
FONT = "Segoe UI"
MONO = "Cascadia Mono"
SPI_GETWORKAREA = 0x30
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


def work_area() -> tuple[int, int, int, int]:
    rect = wt.RECT()
    if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)


def round_corners(window) -> None:
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
    preference = ctypes.c_int(DWMWCP_ROUND)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(preference),
                                               ctypes.sizeof(preference))


def mix(first: str, second: str, t: float) -> str:
    a = [int(first[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(second[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * t):02x}" for x, y in zip(a, b))


def scale_of(root) -> float:
    return float(root._get_window_scaling())
