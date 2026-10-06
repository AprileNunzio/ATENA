from dataclasses import dataclass, field

from features.twin.model import HomeState, domain_of

BLOCK, WARN = "block", "warn"


@dataclass(frozen=True)
class Conflict:
    rule: str
    severity: str
    culprits: tuple = ()
    subjects: tuple = ()
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "culprits": list(self.culprits), "subjects": list(self.subjects),
                "params": dict(self.params)}


def cameras_while_armed(before: HomeState, after: HomeState, changed: set[str]) -> list[Conflict]:
    armed = after.armed()
    if not armed:
        return []
    off = [e for e in after.states if after.is_camera(e) and after.state(e) == "off" and before.state(e) != "off"]
    culprits = tuple(e for e in off if e in changed)
    return [Conflict("cameras_while_armed", BLOCK, culprits, tuple(armed))] if culprits else []


def access_while_armed(before: HomeState, after: HomeState, changed: set[str]) -> list[Conflict]:
    armed = after.armed()
    if not armed:
        return []
    opened = [e for e in after.by_domain("lock", "cover") if after.open_now(e) and (domain_of(e) == "lock" or after.is_opening(e))]
    caused = tuple(e for e in opened if e in changed)
    if caused:
        return [Conflict("access_while_armed", BLOCK, caused, tuple(armed))]
    newly_armed = tuple(e for e in armed if e in changed)
    still_open = tuple(e for e in opened + [s for s in after.by_domain("binary_sensor") if after.is_opening(s) and after.open_now(s)])
    return [Conflict("armed_with_open_access", WARN, newly_armed, still_open)] if newly_armed and still_open else []


def climate_with_open_window(before: HomeState, after: HomeState, changed: set[str]) -> list[Conflict]:
    out = []
    for eid in after.by_domain("climate"):
        if eid not in changed or after.state(eid) in ("off", None, "unknown"):
            continue
        area = after.area(eid)
        windows = tuple(s for s in after.by_domain("binary_sensor")
                        if after.is_opening(s) and after.open_now(s) and (not area or after.area(s) == area))
        if windows:
            out.append(Conflict("climate_with_open_window", WARN, (eid,), windows))
    return out


def valve_unattended(before: HomeState, after: HomeState, changed: set[str]) -> list[Conflict]:
    if after.meta.get("people", 1):
        return []
    opened = tuple(e for e in after.by_domain("valve") if e in changed and after.state(e) == "open")
    return [Conflict("valve_unattended", BLOCK, opened)] if opened else []


RULES = {
    "cameras_while_armed": cameras_while_armed,
    "access_while_armed": access_while_armed,
    "climate_with_open_window": climate_with_open_window,
    "valve_unattended": valve_unattended,
}
