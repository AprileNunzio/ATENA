from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet

def discover_languages(base_path: str = "server") -> FrozenSet[str]:
    root = Path(base_path)
    if not root.exists():
        return frozenset(["en", "it"])
    found = {p.stem for p in root.rglob("*.json") if p.parent.name == "language"}
    return frozenset(found) if found else frozenset(["en", "it"])

@dataclass(frozen=True)
class I18nConfig:
    default_language: str = "en"
    base_dir: str = "server"
    
    @property
    def supported_languages(self) -> FrozenSet[str]:
        return discover_languages(self.base_dir)
