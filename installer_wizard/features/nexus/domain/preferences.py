import re
from dataclasses import dataclass, field, replace

LEVELS = ("explorer", "pilot", "architect")
DEFAULT_LEVEL = "pilot"
MAX_FAVORITES = 24
_TOOL_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")


@dataclass(frozen=True)
class Preferences:
    level: str = DEFAULT_LEVEL
    favorites: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {"level": self.level, "favorites": list(self.favorites)}


def _level(value) -> str:
    if value not in LEVELS:
        raise ValueError("Livello non valido: scegli explorer, pilot o architect")
    return value


def _favorites(value) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_FAVORITES:
        raise ValueError(f"I preferiti devono essere un elenco di al massimo {MAX_FAVORITES} strumenti")
    if not all(isinstance(item, str) and _TOOL_ID.match(item) for item in value):
        raise ValueError("Identificativo di strumento non valido nei preferiti")
    return tuple(dict.fromkeys(value))


def restore(raw) -> Preferences:
    if not isinstance(raw, dict):
        return Preferences()
    try:
        return Preferences(level=_level(raw.get("level", DEFAULT_LEVEL)), favorites=_favorites(raw.get("favorites", [])))
    except ValueError:
        return Preferences()


def amend(current: Preferences, update) -> Preferences:
    if not isinstance(update, dict) or not update:
        raise ValueError("Nessuna preferenza da salvare")
    unknown = set(update) - {"level", "favorites"}
    if unknown:
        raise ValueError(f"Preferenza sconosciuta: {', '.join(sorted(unknown))}")
    changed = current
    if "level" in update:
        changed = replace(changed, level=_level(update["level"]))
    if "favorites" in update:
        changed = replace(changed, favorites=_favorites(update["favorites"]))
    return changed
