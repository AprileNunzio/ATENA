"""I sensi del PC: finestra su cui l'utente lavora, testo e immagine di quella finestra, webcam, cartelle e app."""
import ctypes
import ctypes.wintypes as wt
import io
import logging
import os
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger("atena.senses")
user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
OWN_PID = os.getpid()
MAX_SIDE = 1600

KNOWN_FOLDERS = {
    "Scrivania": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "Documenti": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "Download": "374DE290-123F-4565-9164-39C4925E467B",
    "Immagini": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "Musica": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "Video": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]


def known_folder(guid: str) -> str:
    u = uuid.UUID(guid)
    g = _GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
    path = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(path)) != 0:
        return ""
    try:
        return path.value or ""
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path)


def folders() -> dict:
    out = {"Cartella utente": str(Path.home())}
    for name, guid in KNOWN_FOLDERS.items():
        p = known_folder(guid)
        if p:
            out[name] = p
    return out


def _start_menu_dirs() -> list[Path]:
    return [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
            Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs"]


_SKIP_APP = ("uninstall", "disinstalla", "readme", "leggimi", "help", "guida", "license", "licenza", "website", "sito web")


def installed_apps() -> dict[str, str]:
    """Nome visibile → collegamento .lnk del menu Start."""
    apps: dict[str, str] = {}
    for root in _start_menu_dirs():
        if not root.is_dir():
            continue
        for lnk in root.rglob("*.lnk"):
            name = lnk.stem
            if not any(s in name.lower() for s in _SKIP_APP):
                apps.setdefault(name, str(lnk))
    return apps


class Window:
    def __init__(self, hwnd: int, title: str, app: str, pid: int) -> None:
        self.hwnd, self.title, self.app, self.pid = hwnd, title, app, pid


def _window_info(hwnd: int) -> Window | None:
    if not hwnd:
        return None
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == OWN_PID:
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value.strip()
    if not title or title in ("Program Manager",):
        return None
    app = ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        size = wt.DWORD(1024)
        path = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            app = Path(path.value).stem
        kernel32.CloseHandle(handle)
    return Window(hwnd, title, app, pid.value)


class Focus(threading.Thread):
    """Ricorda l'ultima finestra esterna attiva: quando l'utente parla o clicca su ATENA, sa su cosa stava lavorando."""

    def __init__(self) -> None:
        super().__init__(daemon=True, name="focus")
        self.last: Window | None = None

    def run(self) -> None:
        while True:
            try:
                w = _window_info(user32.GetForegroundWindow())
                if w:
                    self.last = w
            except Exception:
                pass
            time.sleep(0.6)

    def current(self) -> Window | None:
        w = self.last
        return w if w and user32.IsWindow(w.hwnd) else None

    def bring_back(self) -> bool:
        w = self.current()
        if not w:
            return False
        if user32.IsIconic(w.hwnd):
            user32.ShowWindow(w.hwnd, 9)  # SW_RESTORE
        # ALT premuto per un attimo: Windows consente allora di cambiare la finestra in primo piano
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        ok = bool(user32.SetForegroundWindow(w.hwnd))
        time.sleep(0.25)
        return ok


def window_text(w: Window, limit: int = 20000, budget: float = 3.0) -> str:
    """Testo leggibile della finestra (documenti, editor, pagine) tramite UI Automation."""
    try:
        import uiautomation as auto
    except ImportError:
        return ""
    texts: list[str] = []
    started = time.time()
    try:
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(w.hwnd)
            if not root:
                return ""
            for control, depth in auto.WalkControl(root, includeTop=True, maxDepth=30):
                if time.time() - started > budget or sum(map(len, texts)) > limit:
                    break
                kind = control.ControlType
                if kind == auto.ControlType.DocumentControl or kind == auto.ControlType.EditControl:
                    value = ""
                    try:
                        pattern = control.GetPattern(auto.PatternId.TextPattern)
                        if pattern:
                            value = pattern.DocumentRange.GetText(limit)
                    except Exception:
                        pass
                    if not value:
                        try:
                            pattern = control.GetPattern(auto.PatternId.ValuePattern)
                            value = pattern.Value if pattern else ""
                        except Exception:
                            value = ""
                    if value and value.strip():
                        texts.append(value.strip())
                elif kind == auto.ControlType.TextControl and control.Name and len(control.Name) > 3:
                    texts.append(control.Name.strip())
    except Exception as exc:
        log.info("Testo della finestra non leggibile: %s", exc)
    seen, unique = set(), []
    for t in texts:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return "\n".join(unique)[:limit]


def _jpeg(img) -> bytes:
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=82)
    return buf.getvalue()


def window_image(w: Window | None) -> bytes:
    import mss
    from PIL import Image
    with mss.mss() as shot:
        region = shot.monitors[1]
        if w:
            rect = wt.RECT()
            if user32.GetWindowRect(w.hwnd, ctypes.byref(rect)) and rect.right - rect.left > 50 and rect.bottom - rect.top > 50:
                region = {"left": rect.left, "top": rect.top, "width": rect.right - rect.left, "height": rect.bottom - rect.top}
        raw = shot.grab(region)
        return _jpeg(Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX"))


def webcam_image(index: int = 0) -> bytes:
    """Un solo fotogramma: la webcam si accende solo per l'istante dello scatto."""
    import cv2
    from PIL import Image
    cam = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    try:
        if not cam.isOpened():
            raise RuntimeError("Webcam non trovata o già in uso da un altro programma")
        frame = None
        for _ in range(8):  # i primi fotogrammi sono scuri mentre l'esposizione si regola
            ok, img = cam.read()
            if ok:
                frame = img
            time.sleep(0.05)
        if frame is None:
            raise RuntimeError("La webcam non ha restituito immagini")
        return _jpeg(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    finally:
        cam.release()
