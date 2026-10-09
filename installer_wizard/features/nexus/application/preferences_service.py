from features.nexus.application.ports import PreferencesRepository
from features.nexus.domain.preferences import Preferences, amend, restore


class PreferencesService:
    def __init__(self, repository: PreferencesRepository) -> None:
        self.repository = repository

    def get(self, user: str) -> Preferences:
        return restore(self.repository.load(user))

    def update(self, user: str, changes) -> Preferences:
        updated = amend(self.get(user), changes)
        self.repository.save(user, updated.as_dict())
        return updated
