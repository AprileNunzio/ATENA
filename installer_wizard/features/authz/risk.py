from enum import IntEnum


class Risk(IntEnum):
    INFO = 0
    HOME = 1
    PERSONAL = 2
    FILES = 3
    CRITICAL = 4


NAMES = {r.name.lower(): r for r in Risk}

TOOLS: dict[str, Risk] = {
    "now": Risk.INFO, "list_widgets": Risk.INFO, "avatar_catalog": Risk.INFO, "list_models": Risk.INFO,
    "team_roster": Risk.INFO, "agent_info": Risk.INFO, "agent_inbox": Risk.INFO, "list_automations": Risk.INFO,
    "list_tasks": Risk.INFO, "list_custom_tools": Risk.INFO, "music_now": Risk.INFO, "music_search": Risk.INFO,
    "music_outputs": Risk.INFO,
    "show_widget": Risk.HOME, "hide_widget": Risk.HOME, "move_widget": Risk.HOME, "avatar": Risk.HOME,
    "show_model": Risk.HOME, "run_automation": Risk.HOME, "toggle_automation": Risk.HOME, "emit_event": Risk.HOME,
    "agent_tell": Risk.HOME, "agent_ask": Risk.HOME, "close_camera": Risk.HOME, "music_control": Risk.HOME,
    "music_play": Risk.HOME,
    **{f"board_{n}": Risk.HOME for n in ("callout", "chart", "chemistry", "clear", "close", "draw", "formula", "image",
                                         "language", "lesson", "look", "mark", "new_page", "open", "physics", "plot",
                                         "solve", "table", "write")},
    "find_contact": Risk.PERSONAL, "list_dir": Risk.PERSONAL, "read_file": Risk.PERSONAL, "find_files": Risk.PERSONAL,
    "file_info": Risk.PERSONAL, "camera_events": Risk.PERSONAL, "camera_overview": Risk.PERSONAL,
    "list_cameras": Risk.PERSONAL, "open_camera": Risk.PERSONAL,
    "write_file": Risk.FILES, "make_dir": Risk.FILES, "copy": Risk.FILES, "move": Risk.FILES, "zip": Risk.FILES,
    "create_site": Risk.FILES, "create_3d": Risk.FILES, "create_document": Risk.FILES, "copy_to_share": Risk.FILES,
    "camera_photo": Risk.FILES, "create_widget": Risk.FILES, "delete_widget": Risk.FILES,
    "send_email": Risk.CRITICAL, "share_folder": Risk.CRITICAL, "delete": Risk.CRITICAL, "packages": Risk.CRITICAL,
    "rpa_run": Risk.CRITICAL, "run_command": Risk.CRITICAL, "http_get": Risk.CRITICAL,
    "create_automation": Risk.CRITICAL, "schedule_task": Risk.CRITICAL, "cancel_task": Risk.CRITICAL,
    "run_task_now": Risk.CRITICAL, "agent_set": Risk.CRITICAL,
    "camera_motion": Risk.CRITICAL, "create_feature": Risk.CRITICAL, "delete_feature": Risk.CRITICAL,
    "create_tool": Risk.CRITICAL, "delete_tool": Risk.CRITICAL,
}

CONNECTORS: dict[str, Risk] = {
    "vault": Risk.PERSONAL, "documents": Risk.PERSONAL, "gservices": Risk.PERSONAL, "maps": Risk.PERSONAL,
    "vision": Risk.PERSONAL, "livecam": Risk.PERSONAL, "people": Risk.PERSONAL, "person_info": Risk.PERSONAL,
    "selftest": Risk.HOME, "sounds": Risk.HOME, "whiteboard": Risk.HOME, "screens": Risk.HOME, "models3d": Risk.HOME,
    "music": Risk.HOME, "home": Risk.HOME, "camera": Risk.PERSONAL,
}


COMPOSED: dict[str, tuple[str, ...]] = {}


def of_tool(name: str, seen: frozenset[str] = frozenset()) -> Risk:
    if name in TOOLS:
        return TOOLS[name]
    steps = COMPOSED.get(name)
    if not steps or name in seen:
        return Risk.CRITICAL
    return max(of_tool(step, seen | {name}) for step in steps)


def compose(name: str, steps: list[str]) -> None:
    COMPOSED[name] = tuple(steps)


def forget(name: str) -> None:
    COMPOSED.pop(name, None)


def of_connector(name: str) -> Risk:
    return CONNECTORS.get(name, Risk.INFO)


def parse(name: str) -> Risk | None:
    return NAMES.get(str(name or "").strip().lower())
