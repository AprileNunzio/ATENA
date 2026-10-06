PRIORITY = {
    "laws": 100, "vault": 95, "selftest": 90, "governor": 85, "auto_update": 80, "ear": 78, "vision": 75, "people": 72, "home_assistant": 70,
    "cameras": 65, "desktop": 60, "kiosk": 58, "nodes": 56, "autonomy": 55, "automations": 52, "scheduler": 52, "agent": 50, "chat": 50,
    "brain": 50, "documents": 40, "models3d": 35, "shares": 35, "whiteboard": 40, "music": 30, "sounds": 30, "spotify": 28, "appearance": 20,
}
DEFAULT = 45
MODULE_OWNER = {
    "features.agent.tools_comm": "telegram", "features.agent.tools_display": "desktop", "features.agent.tools_files": "shares",
    "features.agent.tools_rpa": "rpa", "features.agent.tools_system": "actions", "features.autonomy.tools": "autonomy",
    "features.automations.tools": "automations", "features.documents.tools": "documents", "features.agent.tools_media": "music",
    "features.team.tools": "agent",
}


def of(agent_id: str) -> int:
    return PRIORITY.get(agent_id, DEFAULT)
