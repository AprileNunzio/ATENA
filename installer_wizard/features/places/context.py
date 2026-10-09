import re

from features.places.locate import current_room, locator
from features.places.store import Room

NODE_ID = re.compile(r"^[\w.-]{1,64}$")
FIXED = {"kiosk": "display:kiosk", "admin": "", "remote": ""}


def request_key(device: str) -> str:
    if device in FIXED:
        return FIXED[device]
    return f"node:{device}" if NODE_ID.match(device or "") else ""


def enter(who: str, source: str, device: str) -> Room | None:
    room = locator.resolve(who, source or request_key(device))
    current_room.set(room)
    return room


def _same(a: str, b: str) -> bool:
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def area() -> str:
    room = current_room.get()
    if room is None:
        return ""
    if room.ha_area:
        return room.ha_area
    from features.home_assistant.home import brain
    names = [room.name, *room.aliases]
    return next((aid for aid, a in (getattr(brain, "areas", {}) or {}).items()
                 if any(_same(a.get("name", ""), n) for n in names)), "")
