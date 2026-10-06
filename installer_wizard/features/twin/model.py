import copy
import re

CAMERA_WORDS = re.compile(r"camera|telecamer|cctv|nvr|webcam|videosorveglian", re.I)
GATE_WORDS = re.compile(r"garage|gate|cancell|portone|door|porta|basculante|serrand", re.I)
OPENINGS = {"door", "window", "opening", "garage_door"}

EFFECTS = {
    "turn_on": "on", "turn_off": "off", "lock": "locked", "unlock": "unlocked", "open": "unlocked",
    "open_cover": "open", "close_cover": "closed", "stop_cover": None, "open_valve": "open", "close_valve": "closed",
    "alarm_disarm": "disarmed", "alarm_arm_home": "armed_home", "alarm_arm_away": "armed_away",
    "alarm_arm_night": "armed_night", "alarm_arm_vacation": "armed_vacation", "alarm_arm_custom_bypass": "armed_custom_bypass",
    "media_play": "playing", "media_pause": "paused", "media_stop": "idle", "enable_motion_detection": None,
}


def domain_of(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


def predicted_state(entity_id: str, service: str, data: dict, current: str | None) -> str | None:
    domain = domain_of(entity_id)
    if service == "toggle":
        on = {"lock": ("locked", "unlocked"), "cover": ("closed", "open"), "valve": ("closed", "open")}.get(domain, ("off", "on"))
        return on[1] if current == on[0] else on[0]
    if service == "set_hvac_mode":
        return str(data.get("hvac_mode") or current)
    if service in ("set_cover_position", "set_valve_position"):
        return "closed" if int(data.get("position", 0) or 0) == 0 else "open"
    if domain == "camera" and service in ("turn_on", "turn_off"):
        return "idle" if service == "turn_on" else "off"
    if domain == "climate" and service == "turn_on":
        return current if current not in (None, "off") else "heat"
    return EFFECTS.get(service, current)


class HomeState:
    def __init__(self, states: dict, meta: dict | None = None) -> None:
        self.states = {eid: {"state": str((st or {}).get("state")), "attrs": dict((st or {}).get("attrs") or {})}
                       for eid, st in states.items()}
        self.meta = dict(meta or {})

    def clone(self) -> "HomeState":
        twin = HomeState({}, self.meta)
        twin.states = copy.deepcopy(self.states)
        return twin

    def state(self, eid: str) -> str | None:
        st = self.states.get(eid)
        return st["state"] if st else None

    def attr(self, eid: str, name: str, default=""):
        st = self.states.get(eid)
        return (st or {}).get("attrs", {}).get(name, default)

    def area(self, eid: str) -> str:
        return str(self.attr(eid, "area_id", "") or self.meta.get("areas", {}).get(eid, ""))

    def apply(self, domain: str, service: str, entity_ids: list[str], data: dict) -> list[tuple[str, str | None, str | None]]:
        changes = []
        for eid in entity_ids:
            before = self.state(eid)
            after = predicted_state(eid, service, data or {}, before)
            if after is None:
                continue
            self.states.setdefault(eid, {"state": "unknown", "attrs": {}})["state"] = after
            changes.append((eid, before, after))
        return changes

    def by_domain(self, *domains: str) -> list[str]:
        return [eid for eid in self.states if domain_of(eid) in domains]

    def armed(self) -> list[str]:
        return [eid for eid in self.by_domain("alarm_control_panel") if str(self.state(eid)).startswith("armed")]

    def is_camera(self, eid: str) -> bool:
        domain = domain_of(eid)
        if domain == "camera":
            return True
        name = f"{eid} {self.attr(eid, 'friendly_name', '')}"
        return domain in ("switch", "input_boolean") and bool(CAMERA_WORDS.search(name))

    def is_opening(self, eid: str) -> bool:
        domain = domain_of(eid)
        if domain == "binary_sensor":
            return self.attr(eid, "device_class", "") in OPENINGS
        return domain == "cover" and bool(GATE_WORDS.search(f"{eid} {self.attr(eid, 'friendly_name', '')}"))

    def open_now(self, eid: str) -> bool:
        st = self.state(eid)
        return st in ("on", "open", "opening") if domain_of(eid) in ("binary_sensor", "cover") else st == "unlocked"
