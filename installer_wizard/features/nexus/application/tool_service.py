import re
from typing import Callable

from features.nexus.domain import wizard
from features.nexus.domain.zones import FAMILIES, classify

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
_SETTING_FIELDS = ("key", "label", "type", "default", "help", "placeholder", "button", "download")


class ToolNotFound(LookupError):
    pass


class ToolService:
    def __init__(self, catalog: Callable[[], dict], badges: Callable[[], dict] = dict) -> None:
        self.catalog = catalog
        self.badges = badges

    @staticmethod
    def _setting(setting: dict) -> dict:
        out = {k: setting[k] for k in _SETTING_FIELDS if k in setting}
        if setting.get("type") in ("select", "bool"):
            out["options"] = wizard.options_of(setting)
        return out

    def detail(self, fid: str) -> dict:
        if not _ID.match(fid or ""):
            raise ToolNotFound(fid)
        listing = self.catalog()
        item = next((f for f in listing.get("features", []) if f.get("id") == fid), None)
        if item is None:
            raise ToolNotFound(fid)
        state = item.get("state") or {}
        placement = classify(item)
        return {
            "id": fid, "name": item.get("name", fid), "icon": item.get("icon", "◆"),
            "description": item.get("description", ""), "capabilities": list(item.get("capabilities") or []),
            "panel": item.get("panel", ""), "source": item.get("source", "system"),
            "toggle": bool(item.get("toggle")), "pinned": bool(item.get("pinned")),
            "enabled": bool(state.get("enabled")), "mode": state.get("mode", "1"), "reason": state.get("reason", ""),
            "fixed": bool(state.get("fixed")), "risk": bool(state.get("risk")),
            "requires": item.get("requires") or {}, **placement.as_dict(),
            "family_label": FAMILIES.get(placement.family, ""),
            "settings": [self._setting(s) for s in item.get("settings") or []],
            "values": item.get("values") or {},
            "wizard": wizard.build(item),
            "hardware": listing.get("hardware") or {},
            **self.badges().get(fid, {"badge": "", "since": 0}),
        }
