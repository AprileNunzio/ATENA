from config import STATE_DIR

from features.nexus.application.preferences_service import PreferencesService
from features.nexus.infrastructure.json_preferences import JsonPreferencesRepository

preferences = PreferencesService(JsonPreferencesRepository(STATE_DIR / "nexus" / "preferences.json"))
