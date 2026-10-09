from pathlib import Path

import packages
from config import STATE_DIR, read_env
from feature_registry import registry
from state import store
from steps import STEPS

from features.autonomy import approvals
from features.nexus.application.awakening_service import AwakeningService
from features.nexus.application.freshness_service import FreshnessService
from features.nexus.application.preferences_service import PreferencesService
from features.nexus.application.summary_service import SummaryService
from features.nexus.application.tool_service import ToolService
from features.nexus.infrastructure.fingerprint import FolderFingerprint
from features.nexus.infrastructure.json_preferences import JsonPreferencesRepository
from features.nexus.infrastructure.json_store import JsonDocument


def _catalog() -> dict:
    registry.scan()
    return registry.listing()


def feature_folders() -> dict[str, Path]:
    return {fid: Path(m["dir"]) for fid, m in list(registry.features.items()) if m.get("dir")}


awakening = AwakeningService(JsonDocument(STATE_DIR / "nexus" / "awakening.json"), env=read_env, catalog=_catalog,
                             brain_mode=packages.brain_mode)
freshness = FreshnessService(FolderFingerprint(), JsonDocument(STATE_DIR / "nexus" / "freshness.json"))
preferences = PreferencesService(JsonPreferencesRepository(STATE_DIR / "nexus" / "preferences.json"))
summary = SummaryService(state=lambda: store.snapshot(admin=True, log_lines=0), catalog=_catalog,
                         step_titles=lambda: {s.id: s.title for s in STEPS}, approvals=lambda: len(approvals.pending()),
                         badges=freshness.badges, awakening=awakening.progress)
tools = ToolService(catalog=_catalog, badges=freshness.badges)
