import os
import sys
from pathlib import Path

VERSION = "4.1.10"
FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "ATENA"
CONFIG_FILE = DATA_DIR / "assistant.json"
PERMISSIONS_FILE = DATA_DIR / "permissions.json"
KEY_FILE = DATA_DIR / "integrity.key"
LOG_FILE = DATA_DIR / "assistant.log"
BACKUP_DIR = DATA_DIR / "backup"


def ensure() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
