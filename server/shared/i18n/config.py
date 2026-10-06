from dataclasses import dataclass, field
from typing import FrozenSet

@dataclass(frozen=True)
class I18nConfig:
    default_language: str = "en"
    supported_languages: FrozenSet[str] = field(default_factory=lambda: frozenset(["en", "it"]))
    base_dir: str = "server"
