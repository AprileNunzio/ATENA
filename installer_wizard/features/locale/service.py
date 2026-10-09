from dataclasses import dataclass

from config import UI_LANGUAGES, env_get

from features.locale.store import store
from features.voices import languages

DEFAULT_UI = "it"


@dataclass(frozen=True)
class Reply:
    lang: str
    teach: bool
    source: str


def system_ui() -> str:
    value = env_get("ATENA_UI_LANG", DEFAULT_UI)
    return value if value in UI_LANGUAGES else DEFAULT_UI


def system_reply() -> str:
    for value in (languages.base(env_get("ATENA_REPLY_LANG", "")), languages.base(env_get("ATENA_UI_LANG", ""))):
        if value in languages.LANGS:
            return value
    return languages.DEFAULT


def _profile(slug: str) -> dict:
    if not slug:
        return {}
    from features.people import people
    return people.load(slug) or {}


def valid_ui(lang: str) -> str:
    lang = languages.base(lang)
    if lang and lang not in UI_LANGUAGES:
        raise ValueError(f"lingua dello schermo non supportata: {lang}")
    return lang


def valid_reply(lang: str) -> str:
    lang = languages.base(lang)
    if lang and lang not in languages.LANGS:
        raise ValueError(f"lingua di risposta non supportata: {lang}")
    return lang


def ui_lang(user: str = "", device: str = "", person: str = "") -> str:
    chosen = (str(_profile(person).get("ui_language") or "")
              or (store.get("users", user).get("ui") if user else "")
              or (store.get("devices", device).get("ui") if device else ""))
    return chosen if chosen in UI_LANGUAGES else system_ui()


def set_ui(lang: str, user: str = "", device: str = "", person: str = "") -> str:
    lang = valid_ui(lang)
    if person:
        from features.people import people
        people.update(person, {"ui_language": lang})
    elif user:
        store.put("users", user, ui=lang)
    elif device:
        store.put("devices", device, ui=lang)
    else:
        raise ValueError("serve una persona, un utente o un dispositivo")
    return ui_lang(user, device, person)


def _scope(person: str, device: str) -> tuple[str, str]:
    if person and _profile(person):
        return "people", person
    if device:
        return "devices", device
    raise ValueError("serve una persona o un dispositivo")


def preferred(person: str = "") -> str:
    lang = str(_profile(person).get("voice_language") or "")
    return lang if lang in languages.LANGS else system_reply()


def chosen(person: str = "", device: str = "") -> Reply | None:
    for scope, key in (("people", person), ("devices", device)):
        if not key or (scope == "people" and not _profile(key)):
            continue
        saved = store.get(scope, key)
        lang = saved.get("teach") or saved.get("reply", "")
        if lang in languages.LANGS:
            return Reply(lang, bool(saved.get("teach")), scope)
        if scope == "people":
            return None
    return None


def choose(lang: str, teach: bool = False, person: str = "", device: str = "") -> Reply:
    lang = valid_reply(lang)
    scope, key = _scope(person, device)
    if teach:
        store.put(scope, key, teach=lang)
    else:
        store.put(scope, key, reply=lang, teach="")
    return chosen(person, device) or Reply(lang, teach, scope)


def forget_choice(person: str = "", device: str = "") -> str:
    scope, key = _scope(person, device)
    store.put(scope, key, reply="", teach="")
    return preferred(person)
