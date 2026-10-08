import ctypes
import ctypes.wintypes as wt
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
OWN_PID = os.getpid()
QUERY_LIMITED = 0x1000
SW_RESTORE, SW_MINIMIZE, SW_MAXIMIZE = 9, 6, 3
VK_MENU, KEYUP = 0x12, 2
IGNORED_TITLES = {"Program Manager"}
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


@dataclass(frozen=True)
class Window:
    hwnd: int
    title: str
    app: str
    pid: int


def _title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _app(pid: int) -> str:
    handle = kernel32.OpenProcess(QUERY_LIMITED, False, pid)
    if not handle:
        return ""
    try:
        size = wt.DWORD(1024)
        path = ctypes.create_unicode_buffer(1024)
        return Path(path.value).stem if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)) else ""
    finally:
        kernel32.CloseHandle(handle)


def describe(hwnd: int) -> Window | None:
    if not hwnd:
        return None
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    title = _title(hwnd)
    if pid.value == OWN_PID or not title or title in IGNORED_TITLES:
        return None
    return Window(hwnd, title, _app(pid.value), pid.value)


def visible_windows() -> list[Window]:
    found: list[Window] = []

    def collect(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            window = describe(hwnd)
            if window:
                found.append(window)
        return True

    user32.EnumWindows(EnumProc(collect), 0)
    return found


def find(text: str) -> Window | None:
    wanted = text.strip().lower()
    if not wanted:
        return None
    matches = [w for w in visible_windows() if wanted in w.title.lower() or wanted == w.app.lower()]
    return min(matches, key=lambda w: len(w.title)) if matches else None


def bring_to_front(window: Window) -> bool:
    if user32.IsIconic(window.hwnd):
        user32.ShowWindow(window.hwnd, SW_RESTORE)
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYUP, 0)
    ok = bool(user32.SetForegroundWindow(window.hwnd))
    time.sleep(0.25)
    return ok


def show(window: Window, state: int) -> None:
    user32.ShowWindow(window.hwnd, state)


class Focus(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="focus")
        self.last: Window | None = None

    def run(self) -> None:
        while True:
            window = describe(user32.GetForegroundWindow())
            if window:
                self.last = window
            time.sleep(0.6)

    def current(self) -> Window | None:
        window = self.last
        return window if window and user32.IsWindow(window.hwnd) else None

    def bring_back(self) -> bool:
        window = self.current()
        return bring_to_front(window) if window else False
