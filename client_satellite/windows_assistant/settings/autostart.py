import sys
import winreg
from pathlib import Path

from settings import paths

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ATENA Assistente"


def command() -> str:
    if paths.FROZEN:
        return f'"{Path(sys.executable).resolve()}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreter}" "{paths.APP_DIR / "atena_assistant.py"}"'


def enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
    except FileNotFoundError:
        return False
    return True


def set_enabled(on: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, command())
        elif enabled():
            winreg.DeleteValue(key, RUN_NAME)
