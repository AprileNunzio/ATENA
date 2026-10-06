from features.cameras import commands as camera_commands
from features.desktop.desk import desk
from features.music import commands
from features.music.outputs import outputs

STATE = {"pause": "paused", "resume": "playing"}


def playing(args: dict, result: str) -> str | None:
    return None if commands.active_device() else "nessuna riproduzione risulta attiva"


def controlled(args: dict, result: str) -> str | None:
    action = args.get("action")
    device_id = commands.active_device()
    if action == "stop":
        return None if device_id is None else "la musica risulta ancora attiva"
    if device_id is None:
        return "nessuna riproduzione risulta attiva"
    session = outputs.sessions[device_id]
    if action in STATE and session.state != STATE[action]:
        return f"lo stato è «{session.state}» invece di «{STATE[action]}»"
    if action == "volume" and abs(session.volume - max(0.0, min(100.0, float(args.get("value", 0)))) / 100) > 0.011:
        return "il volume non è cambiato"
    return None


def camera_opened(args: dict, result: str) -> str | None:
    keys = camera_commands.open_keys()
    if not keys:
        return "il widget della telecamera non risulta aperto"
    if str(args.get("fullscreen", "")).lower() == "true" and not any(desk.instances.get(k, {}).get("fullscreen") for k in keys):
        return "il widget non risulta a tutto schermo"
    return None


def camera_closed(args: dict, result: str) -> str | None:
    if not args.get("name") and camera_commands.open_keys():
        return "alcune telecamere risultano ancora aperte"
    return None
