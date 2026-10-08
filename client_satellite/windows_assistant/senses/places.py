import ctypes
import ctypes.wintypes as wt
import os
import uuid
from pathlib import Path

KNOWN_FOLDERS = {
    "Scrivania": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "Documenti": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "Download": "374DE290-123F-4565-9164-39C4925E467B",
    "Immagini": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "Musica": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "Video": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}
SKIP_APPS = ("uninstall", "disinstalla", "readme", "leggimi", "help", "guida", "license", "licenza", "website", "sito web")


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]


def known_folder(guid: str) -> str:
    u = uuid.UUID(guid)
    native = _GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
    path = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(native), 0, None, ctypes.byref(path)) != 0:
        return ""
    try:
        return path.value or ""
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path)


def folders() -> dict[str, str]:
    out = {"Cartella utente": str(Path.home())}
    for name, guid in KNOWN_FOLDERS.items():
        location = known_folder(guid)
        if location:
            out[name] = location
    return out


def start_menu_dirs() -> list[Path]:
    return [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
            Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs"]


def installed_apps() -> dict[str, str]:
    apps: dict[str, str] = {}
    for root in start_menu_dirs():
        if not root.is_dir():
            continue
        for shortcut in root.rglob("*.lnk"):
            if not any(word in shortcut.stem.lower() for word in SKIP_APPS):
                apps.setdefault(shortcut.stem, str(shortcut))
    return apps
