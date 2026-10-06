import os


def number(key: str, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(os.environ.get(key, default))))
    except (TypeError, ValueError):
        return default


def flag(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() not in ("0", "off", "no", "false")


def text(key: str, default: str, allowed: tuple) -> str:
    value = os.environ.get(key, default).strip().lower()
    return value if value in allowed else default
