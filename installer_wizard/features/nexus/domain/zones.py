from dataclasses import dataclass

ZONES = ("home", "brain", "flows", "tools", "trust", "network", "system", "observatory")
FAMILIES = {
    "perception": "Percezione",
    "home": "Casa",
    "communication": "Comunicazione",
    "leisure": "Svago",
    "productivity": "Produttività",
}
LEVELS = ("explorer", "pilot", "architect")

_PLACES = {
    "brain": ("brain", ""), "understanding": ("brain", ""), "team": ("brain", ""), "mind": ("brain", ""),
    "vault": ("brain", ""), "study": ("brain", ""), "soup": ("brain", ""), "cloud": ("brain", ""),
    "vision": ("tools", "perception"), "cameras": ("tools", "perception"), "ear": ("tools", "perception"),
    "hands": ("tools", "perception"), "scene": ("tools", "perception"), "bluetooth": ("tools", "perception"),
    "location": ("tools", "perception"), "devices": ("tools", "perception"), "biometrics": ("tools", "perception"),
    "home_assistant": ("tools", "home"), "places": ("tools", "home"), "people": ("tools", "home"),
    "habits": ("tools", "home"), "twin": ("tools", "home"), "nvr": ("tools", "home"), "redalert": ("tools", "home"),
    "printers": ("tools", "home"),
    "chat": ("tools", "communication"), "telegram": ("tools", "communication"), "google": ("tools", "communication"),
    "spotify": ("tools", "communication"), "mcpclient": ("tools", "communication"),
    "music": ("tools", "leisure"), "tv": ("tools", "leisure"), "sports": ("tools", "leisure"),
    "models3d": ("tools", "leisure"), "avatars": ("tools", "leisure"), "voices": ("tools", "leisure"),
    "voicestudio": ("tools", "leisure"), "sounds": ("tools", "leisure"), "appearance": ("tools", "leisure"),
    "ducking": ("tools", "leisure"),
    "laws": ("trust", ""), "autonomy": ("trust", ""), "capabilities": ("trust", ""), "authz": ("trust", ""),
    "secure": ("trust", ""),
    "firewall": ("network", ""), "vpn": ("network", ""), "network": ("network", ""), "shares": ("network", ""),
    "auto_update": ("system", ""), "nodes": ("system", ""), "proxmox": ("system", ""), "governor": ("system", ""),
    "scheduler": ("system", ""), "kiosk": ("system", ""), "locale": ("system", ""), "selftest": ("system", ""),
}
_BY_CATEGORY = {
    "assistente": ("tools", "productivity"),
    "percezione": ("tools", "perception"),
    "casa": ("tools", "home"),
    "conoscenza": ("brain", ""),
    "comunicazione": ("tools", "communication"),
    "intrattenimento": ("tools", "leisure"),
    "sistema": ("system", ""),
}
_EXPLORER = frozenset({"chat", "vision", "ear", "home_assistant", "music", "voices", "spotify", "people", "auto_update",
                       "laws", "brain", "telegram", "tv", "appearance", "avatars"})
_ARCHITECT = frozenset({"mcpclient", "rpa", "proxmox", "nodes", "soup", "forge", "capabilities", "authz", "governor",
                        "scheduler", "vault", "secure", "kiosk"})


@dataclass(frozen=True)
class Placement:
    zone: str
    family: str
    level: str

    def as_dict(self) -> dict:
        return {"zone": self.zone, "family": self.family, "level": self.level}


def _default_level(fid: str) -> str:
    if fid in _EXPLORER:
        return "explorer"
    return "architect" if fid in _ARCHITECT else "pilot"


def classify(manifest: dict) -> Placement:
    fid = str(manifest.get("id", ""))
    zone, family = _PLACES.get(fid) or _BY_CATEGORY.get(manifest.get("category"), ("tools", "productivity"))
    if manifest.get("zone") in ZONES:
        zone = manifest["zone"]
        family = ""
    if zone == "tools":
        family = manifest.get("family") if manifest.get("family") in FAMILIES else (family or "productivity")
    else:
        family = ""
    level = manifest.get("level") if manifest.get("level") in LEVELS else _default_level(fid)
    return Placement(zone, family, level)
