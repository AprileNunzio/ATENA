import re

MAX_STEPS = 12
MAX_OPTIONS = 12
_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
MODE_STEP = {
    "id": "mode", "kind": "mode", "title": "Quando deve funzionare?",
    "text": "In automatico Atena la accende da sola quando l'hardware lo permette.",
    "options": [
        {"value": "auto", "label": "Automatico", "hint": "Decide Atena in base all'hardware"},
        {"value": "1", "label": "Sempre attiva", "hint": "Accesa comunque, anche se manca qualcosa"},
        {"value": "0", "label": "Spenta", "hint": "Non la uso"},
    ],
}
_BOOL_OPTIONS = [{"value": "1", "label": "Sì", "hint": ""}, {"value": "0", "label": "No", "hint": ""}]


def _text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def options_of(setting: dict) -> list[dict]:
    if setting.get("type") == "bool":
        return list(_BOOL_OPTIONS)
    out = []
    for option in setting.get("options") or []:
        if isinstance(option, dict):
            value = str(option.get("value", option.get("label", "")))
            out.append({"value": value, "label": _text(option.get("label", value), 80), "hint": _text(option.get("hint"), 120)})
        else:
            out.append({"value": str(option), "label": _text(option, 80), "hint": ""})
    return out


def _from_setting(setting: dict) -> dict | None:
    kind = setting.get("type", "text")
    if kind in ("link", "color"):
        return None
    step = {"id": f"set-{setting['key']}", "setting": setting["key"], "title": _text(setting.get("label"), 140),
            "text": _text(setting.get("help"), 300)}
    if kind in ("select", "bool"):
        options = options_of(setting)
        if not 2 <= len(options) <= MAX_OPTIONS:
            return {**step, "kind": "field", "input": "text"}
        return {**step, "kind": "choice", "options": options}
    return {**step, "kind": "field", "input": {"number": "number", "secret": "password"}.get(kind, "text"),
            "placeholder": _text(setting.get("placeholder"), 80)}


def _declared(manifest: dict, settings: dict) -> list[dict]:
    steps = []
    for raw in manifest.get("wizard") or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("kind") == "mode" and manifest.get("toggle"):
            steps.append({**MODE_STEP, "title": _text(raw.get("title"), 140) or MODE_STEP["title"]})
            continue
        key = raw.get("setting")
        if not isinstance(key, str) or not _KEY.match(key) or key not in settings:
            continue
        step = _from_setting(settings[key])
        if step:
            step["title"] = _text(raw.get("title"), 140) or step["title"]
            step["text"] = _text(raw.get("text"), 300) or step["text"]
            steps.append(step)
    return steps


def build(manifest: dict) -> list[dict]:
    settings = {s["key"]: s for s in manifest.get("settings") or [] if isinstance(s, dict) and _KEY.match(str(s.get("key", "")))}
    steps = _declared(manifest, settings)
    if not steps:
        steps = ([dict(MODE_STEP)] if manifest.get("toggle") else []) + [
            step for step in (_from_setting(s) for s in settings.values()) if step]
    return steps[:MAX_STEPS]
