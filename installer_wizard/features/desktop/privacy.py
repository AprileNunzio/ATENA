import time

from config import env_get
from state import store


def flag(key: str, default: bool) -> bool:
    raw = env_get(key, "")
    return default if raw == "" else raw.strip().lower() not in ("0", "off", "no", "false")


def number(key: str, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(env_get(key, str(default)))))
    except (TypeError, ValueError):
        return default


class Privacy:

    def __init__(self) -> None:
        self.gone_since: float | None = None

    @staticmethod
    def enabled() -> bool:
        return flag("ATENA_PRIVACY_AUTOCLOSE", True)

    @staticmethod
    def away_seconds() -> float:
        return number("ATENA_PRIVACY_AWAY_S", 10, 3, 600)

    @staticmethod
    def voice_seconds() -> float:
        return number("ATENA_PRIVACY_VOICE_S", 30, 0, 600)

    def watch(self) -> None:
        presence = store.presence or {}
        if presence.get("status") == "ok" and not presence.get("people"):
            self.gone_since = self.gone_since or time.time()
        else:
            self.gone_since = None

    @property
    def away(self) -> bool:
        return self.enabled() and self.gone_since is not None and time.time() - self.gone_since >= self.away_seconds()

    def view(self) -> dict:
        on = self.enabled()
        return {"enabled": on, "away": self.away, "voice_s": self.voice_seconds() if on else 0}


privacy = Privacy()
