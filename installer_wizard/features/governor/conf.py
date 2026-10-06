from config import env_get


def number(key: str, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(env_get(key, str(default)))))
    except ValueError:
        return default


def flag(key: str, default: bool = True) -> bool:
    raw = env_get(key, "1" if default else "0").strip().lower()
    return raw not in ("0", "off", "no", "false")


def choice(key: str, default: str, allowed: tuple) -> str:
    value = env_get(key, default).strip().lower()
    return value if value in allowed else default
