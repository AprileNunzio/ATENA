from pathlib import Path

import psutil

from config import DEMO, read_env

CLASSES = ("pi", "small", "standard", "powerful")
LABELS = {"pi": "Raspberry Pi", "small": "Computer leggero", "standard": "Computer standard", "powerful": "Computer potente"}
SUGGESTED = {"pi": (), "small": (), "standard": ("voice", "ear"), "powerful": ("voice", "ear", "documents")}
HEAVY = {"pi": {"brain_local", "convert3d", "native", "vision", "documents"}, "small": {"brain_local", "convert3d"},
         "standard": set(), "powerful": set()}
BRAIN = {"pi": "cloud", "small": "cloud", "standard": "local", "powerful": "local"}
MODEL_TREE = Path("/proc/device-tree/model")


def board() -> str:
    try:
        model = MODEL_TREE.read_text(encoding="utf-8", errors="replace").strip("\x00 \n")
    except OSError:
        return ""
    return model[:80] if "raspberry" in model.lower() else ""


def ram_gb() -> float:
    return psutil.virtual_memory().total / 2 ** 30


def detect(gpu: bool = False) -> str:
    if board():
        return "pi"
    ram = ram_gb()
    if ram < 7.5:
        return "small"
    if gpu or ram >= 28:
        return "powerful"
    return "standard"


def current(env: dict | None = None) -> str:
    if DEMO:
        return "standard"
    env = read_env() if env is None else env
    value = env.get("ATENA_MACHINE", "")
    return value if value in CLASSES else detect(env.get("ATENA_HW_PROFILE") == "gpu")


def heavy(pkg_id: str, env: dict | None = None) -> bool:
    return pkg_id in HEAVY[current(env)]
