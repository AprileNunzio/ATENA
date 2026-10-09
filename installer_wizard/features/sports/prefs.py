import json
import logging
import re
import threading

from config import STATE_DIR

from features.sports.catalog import BY_CODE

log = logging.getLogger("atena.sports")
HOUSEHOLD = "_casa"
MAX_TEAMS = 12
ALERTS = ("goals", "kickoff", "results", "f1")
_SLUG = re.compile(r"^[a-z0-9_][a-z0-9_-]{0,63}$")
_CODE = re.compile(r"^[A-Z]{3}$")
_COLOR = re.compile(r"^[0-9a-fA-F]{6}$")
_ID = re.compile(r"^\d{1,8}$")


def blank() -> dict:
    return {"teams": [], "f1": False, "f1_drivers": [], "f1_teams": [], "alerts": {k: True for k in ALERTS},
            "proximity": True, "voice": True}


def _text(value, limit: int) -> str:
    return re.sub(r"[\x00-\x1f<>]", "", str(value or ""))[:limit]


def clean(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Preferenze non valide")
    out = blank()
    teams = []
    for t in (raw.get("teams") or [])[:MAX_TEAMS]:
        if not isinstance(t, dict) or t.get("league") not in BY_CODE or not _ID.match(str(t.get("id") or "")):
            raise ValueError("Squadra non valida")
        color = str(t.get("color") or "")
        teams.append({"league": t["league"], "id": str(t["id"]), "name": _text(t.get("name"), 60),
                      "abbr": _text(t.get("abbr"), 5), "color": color if _COLOR.match(color) else ""})
    out["teams"] = list({(t["league"], t["id"]): t for t in teams}.values())
    out["f1"] = bool(raw.get("f1"))
    out["f1_drivers"] = [d for d in dict.fromkeys(str(x).upper() for x in raw.get("f1_drivers") or []) if _CODE.match(d)][:6]
    out["f1_teams"] = [_text(x, 40) for x in dict.fromkeys(raw.get("f1_teams") or []) if str(x).strip()][:4]
    alerts = raw.get("alerts") if isinstance(raw.get("alerts"), dict) else {}
    out["alerts"] = {k: bool(alerts.get(k, True)) for k in ALERTS}
    out["proximity"] = bool(raw.get("proximity", True))
    out["voice"] = bool(raw.get("voice", True))
    return out


class SportsPrefs:
    def __init__(self, path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._data: dict | None = None

    def _all(self) -> dict:
        if self._data is None:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                raw = {}
            except ValueError as exc:
                log.warning("Preferenze sportive illeggibili, riparto da zero: %s", exc)
                raw = {}
            self._data = {}
            for key, value in (raw if isinstance(raw, dict) else {}).items():
                try:
                    if isinstance(key, str) and _SLUG.match(key):
                        self._data[key] = clean(value)
                except ValueError as exc:
                    log.warning("Preferenze sportive di %s scartate: %s", key, exc)
        return self._data

    def get(self, slug: str) -> dict:
        return dict(self._all().get(slug) or blank())

    def put(self, slug: str, raw: dict) -> dict:
        if not _SLUG.match(slug):
            raise ValueError("Persona non valida")
        value = clean(raw)
        with self._lock:
            data = self._all()
            data[slug] = value
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        return value

    def everyone(self) -> dict[str, dict]:
        return dict(self._all())

    def followed_teams(self) -> dict[tuple[str, str], dict]:
        out: dict[tuple[str, str], dict] = {}
        for slug, p in self._all().items():
            for t in p["teams"]:
                out.setdefault((t["league"], t["id"]), {**t, "fans": []})["fans"].append(slug)
        return out

    def f1_fans(self) -> list[str]:
        return [slug for slug, p in self._all().items() if p["f1"]]


prefs = SportsPrefs(STATE_DIR / "sports.json")
