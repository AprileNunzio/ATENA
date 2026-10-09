from typing import Protocol


class PreferencesRepository(Protocol):
    def load(self, user: str) -> dict | None: ...

    def save(self, user: str, data: dict) -> None: ...
