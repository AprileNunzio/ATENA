import re
import time

from features.home_assistant.nlu.text import norm, phrase_stems

WHERE = re.compile(r"\b(dov ?e|dove sono|dove ho (messo|lasciato)|hai visto|where (is|are|did)|have you seen)\b")
READY = re.compile(r"\b(pront[oiae]|tutto a posto|ready|all set)\b")
MESSAGES = {
    "it": {
        "never": "Non ho mai visto {name}, signore: le telecamere non l'hanno ancora inquadrato.",
        "held": "L'ultima volta, {when}, {name} era in mano a {who}.", "someone": "qualcuno",
        "on": "L'ho visto {when} su {place}{coords}.", "in": "L'ho visto {when} in {place}{coords}.",
        "frame": "L'ho visto {when} nell'inquadratura della telecamera.", "coords": " (coordinate {x}, {y}, {z} metri)",
        "ready": "Sì, signore: per «{profile}» è tutto a posto.", "not_ready": "Non ancora, signore: {problems}.",
        "unknown": "non ho mai visto {item}", "stale": "non vedo {item} da tempo", "elsewhere": "{item} è {where}",
        "elsewhere_on": "{item} è su {where}", "away": "altrove",
        "now": "pochi secondi fa", "minute": "un minuto fa", "minutes": "{n} minuti fa", "hour": "un'ora fa", "hours": "{n} ore fa",
    },
    "en": {
        "never": "I have never seen {name}, sir: no camera has framed it yet.",
        "held": "Last time, {when}, {name} was in {who}'s hands.", "someone": "someone",
        "on": "I saw it {when} on {place}{coords}.", "in": "I saw it {when} in {place}{coords}.",
        "frame": "I saw it {when} in the camera view.", "coords": " (coordinates {x}, {y}, {z} metres)",
        "ready": "Yes, sir: everything is in place for “{profile}”.", "not_ready": "Not yet, sir: {problems}.",
        "unknown": "I have never seen {item}", "stale": "I have not seen {item} for a while", "elsewhere": "{item} is in {where}",
        "elsewhere_on": "{item} is on {where}", "away": "somewhere else",
        "now": "a few seconds ago", "minute": "a minute ago", "minutes": "{n} minutes ago", "hour": "an hour ago", "hours": "{n} hours ago",
    },
}


def _t(lang: str, key: str, **values) -> str:
    return MESSAGES.get(lang, MESSAGES["it"])[key].format(**values)


def _ago(seconds: float, lang: str) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return _t(lang, "now")
    if minutes < 60:
        return _t(lang, "minutes", n=minutes) if minutes > 1 else _t(lang, "minute")
    hours = minutes // 60
    return _t(lang, "hours", n=hours) if hours > 1 else _t(lang, "hour")


def _match(text: str, entries: list[dict]) -> dict | None:
    words = set(phrase_stems(text))
    best, score = None, 0
    for entry in entries:
        for name in [entry["name"], *entry.get("aliases", [])]:
            stems = set(phrase_stems(name))
            if stems and stems <= words and len(stems) > score:
                best, score = entry, len(stems)
    return best


def describe(seen: dict | None, name: str, now: float, lang: str = "it") -> str:
    if seen is None:
        return _t(lang, "never", name=name)
    when = _ago(now - seen["at"], lang)
    if seen["held"]:
        return _t(lang, "held", when=when, name=name, who=seen["holder"] or _t(lang, "someone"))
    p = seen.get("position")
    coords = _t(lang, "coords", x=p["x"], y=p["y"], z=p["z"]) if p else ""
    if seen["anchor_name"]:
        return _t(lang, "on", when=when, place=seen["anchor_name"], coords=coords)
    if seen["room"]:
        return _t(lang, "in", when=when, place=seen["room"], coords=coords)
    return _t(lang, "frame", when=when)


def answer(text: str, graph, lang: str = "it", now: float | None = None) -> str | None:
    lang = lang if lang in MESSAGES else "it"
    plain = norm(text)
    now = now or time.time()
    if WHERE.search(plain):
        item = _match(text, graph.items())
        return describe(graph.last_seen(item["labels"]), item["name"], now, lang) if item else None
    if READY.search(plain):
        profile = _match(text, graph.profiles())
        if not profile:
            return None
        result = graph.readiness(profile)
        if result["ready"]:
            return _t(lang, "ready", profile=profile["name"])
        problems = []
        for check in result["checks"]:
            if check["status"] in ("unknown", "stale"):
                problems.append(_t(lang, check["status"], item=check["item"]))
            elif check["status"] == "elsewhere":
                seen = check["seen"]
                key = "elsewhere_on" if seen["anchor_name"] else "elsewhere"
                problems.append(_t(lang, key, item=check["item"], where=seen["anchor_name"] or seen["room"] or _t(lang, "away")))
        return _t(lang, "not_ready", problems="; ".join(problems))
    return None
