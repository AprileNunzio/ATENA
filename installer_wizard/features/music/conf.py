import licensing
from config import env_get


def number(key: str, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(env_get(key, str(default)))))
    except (TypeError, ValueError):
        return default


def flag(key: str, default: bool) -> bool:
    raw = env_get(key, "")
    if raw == "":
        return default
    return raw.strip().lower() not in ("0", "off", "no", "false")


def text(key: str, default: str, allowed: tuple) -> str:
    value = env_get(key, default).strip().lower()
    return value if value in allowed else default


def organize() -> bool:
    return flag("ATENA_MUSIC_ORGANIZE", True)


def scan_minutes() -> float:
    return number("ATENA_MUSIC_SCAN_MIN", 15, 1, 1440)


def covers_online() -> bool:
    return flag("ATENA_MUSIC_COVERS", True)


def lyrics_online() -> bool:
    return flag("ATENA_MUSIC_LYRICS", True)


def cast_enabled() -> bool:
    return flag("ATENA_MUSIC_CAST", True)


def subsonic_enabled() -> bool:
    return flag("ATENA_MUSIC_SUBSONIC", False)


def share_links() -> bool:
    return flag("ATENA_MUSIC_SHARE_LINKS", True)


def share_hours() -> float:
    return number("ATENA_MUSIC_SHARE_HOURS", 24, 1, 720)


def transcode_mode() -> str:
    return text("ATENA_MUSIC_TRANSCODE", "auto", ("auto", "never", "always"))


def transcode_kbps() -> int:
    return int(number("ATENA_MUSIC_TRANSCODE_KBPS", 192, 64, 320))


def history_days() -> int:
    return int(number("ATENA_MUSIC_HISTORY_DAYS", 365, 7, 3650))


def radio() -> bool:
    return flag("ATENA_MUSIC_RADIO", True)


def crossfade() -> float:
    return number("ATENA_MUSIC_CROSSFADE", 0, 0, 12)


def voice() -> bool:
    return flag("ATENA_MUSIC_VOICE", True)


def identify() -> bool:
    return flag("ATENA_MUSIC_IDENTIFY", True) and licensing.permitted("shazam")


def write_tags() -> bool:
    return flag("ATENA_MUSIC_TAGS", True)


def rename() -> bool:
    return flag("ATENA_MUSIC_RENAME", True)


def app_password() -> str:
    return env_get("ATENA_MUSIC_APP_PASSWORD", "")
