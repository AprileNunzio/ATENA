from config import STATE_DIR
from feature_registry import registry
from state import store
from steps import STEPS

from features.autonomy import approvals
from features.nexus.application.preferences_service import PreferencesService
from features.nexus.application.summary_service import SummaryService
from features.nexus.infrastructure.json_preferences import JsonPreferencesRepository


def _catalog() -> dict:
    registry.scan()
    return registry.listing()


preferences = PreferencesService(JsonPreferencesRepository(STATE_DIR / "nexus" / "preferences.json"))
summary = SummaryService(state=lambda: store.snapshot(admin=True, log_lines=0), catalog=_catalog,
                         step_titles=lambda: {s.id: s.title for s in STEPS}, approvals=lambda: len(approvals.pending()))
