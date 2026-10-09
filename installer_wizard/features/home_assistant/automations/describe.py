from typing import Callable

STATES = {"on": "acceso", "off": "spento", "open": "aperto", "closed": "chiuso", "home": "a casa",
          "not_home": "fuori casa", "locked": "chiuso a chiave", "unlocked": "aperto", "playing": "in riproduzione",
          "paused": "in pausa", "idle": "inattivo", "heat": "riscaldamento", "cool": "raffrescamento"}
SERVICES = {"turn_on": "accendi", "turn_off": "spegni", "toggle": "inverti", "open_cover": "apri",
            "close_cover": "chiudi", "stop_cover": "ferma", "set_cover_position": "posiziona", "lock": "chiudi a chiave",
            "unlock": "apri la serratura", "set_temperature": "imposta la temperatura di", "media_play": "riproduci",
            "media_pause": "metti in pausa", "volume_set": "imposta il volume di", "trigger": "avvia",
            "start": "avvia", "return_to_base": "riporta alla base", "send_command": "invia un comando a"}
WEEKDAYS = {"mon": "lun", "tue": "mar", "wed": "mer", "thu": "gio", "fri": "ven", "sat": "sab", "sun": "dom"}

Namer = Callable[[str], str]


def _list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _names(value, name: Namer, glue: str = " o ") -> str:
    items = [name(v) if isinstance(v, str) and "{{" not in v else "un'entità variabile" for v in _list(value)]
    if not items:
        return "qualcosa"
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + glue + items[-1]


def _state(value) -> str:
    return " o ".join(STATES.get(str(v), str(v)) for v in _list(value))


def _duration(value) -> str:
    if isinstance(value, dict):
        parts = [f"{value[k]} {u}" for k, u in (("hours", "h"), ("minutes", "min"), ("seconds", "s")) if value.get(k)]
        return " ".join(parts) or "un po'"
    return str(value)


def trigger(t, name: Namer) -> str:
    if isinstance(t, str):
        return "una condizione personalizzata"
    kind = t.get("trigger") or t.get("platform") or ""
    who = _names(t.get("entity_id"), name)
    if kind == "state":
        text = f"{who} diventa {_state(t['to'])}" if "to" in t and t["to"] is not None else f"{who} cambia stato"
        return text + (f" per {_duration(t['for'])}" if t.get("for") else "")
    if kind == "numeric_state":
        limits = [f"sopra {t['above']}" if "above" in t else "", f"sotto {t['below']}" if "below" in t else ""]
        return f"{who} va {' e '.join(x for x in limits if x)}"
    if kind == "time":
        return "alle " + " o alle ".join(name(a) if "." in str(a) else str(a)[:5] for a in _list(t.get("at")))
    if kind == "time_pattern":
        every = [f"{t[k]} {u}" for k, u in (("hours", "ore"), ("minutes", "minuti"), ("seconds", "secondi")) if t.get(k)]
        return "a intervalli regolari (" + ", ".join(every) + ")" if every else "a intervalli regolari"
    if kind == "sun":
        when = "all'alba" if t.get("event") == "sunrise" else "al tramonto"
        return when + (f" ({t['offset']})" if t.get("offset") else "")
    if kind == "zone":
        verb = "entra in" if t.get("event", "enter") == "enter" else "esce da"
        return f"{who} {verb} {name(str(t.get('zone', 'una zona')))}"
    if kind == "homeassistant":
        return "Home Assistant si avvia" if t.get("event") == "start" else "Home Assistant si spegne"
    if kind == "event":
        return f"arriva l'evento «{t.get('event_type', '?')}»"
    if kind == "device":
        return f"un dispositivo segnala «{t.get('type', 'evento')}»"
    if kind == "template":
        return "una condizione personalizzata diventa vera"
    if kind == "webhook":
        return "arriva una chiamata web"
    return f"si verifica «{kind or 'un evento'}»"


def condition(c, name: Namer) -> str:
    if isinstance(c, str):
        return "una condizione personalizzata è vera"
    kind = c.get("condition", "")
    if kind == "state":
        return f"{_names(c.get('entity_id'), name)} è {_state(c.get('state'))}"
    if kind == "numeric_state":
        limits = [f"sopra {c['above']}" if "above" in c else "", f"sotto {c['below']}" if "below" in c else ""]
        return f"{_names(c.get('entity_id'), name)} è {' e '.join(x for x in limits if x)}"
    if kind == "time":
        span = " ".join(x for x in (f"dopo le {str(c['after'])[:5]}" if c.get("after") else "",
                                    f"prima delle {str(c['before'])[:5]}" if c.get("before") else "") if x)
        days = ", ".join(WEEKDAYS.get(d, d) for d in _list(c.get("weekday")))
        return " ".join(x for x in (span, f"({days})" if days else "") if x) or "in un certo orario"
    if kind == "sun":
        return "dopo il tramonto" if c.get("after") == "sunset" or c.get("before") == "sunrise" else "di giorno"
    if kind in ("and", "or", "not"):
        inner = [condition(x, name) for x in _list(c.get("conditions"))]
        glue = {"and": " e ", "or": " oppure ", "not": " e non "}[kind]
        return ("non " if kind == "not" else "") + "(" + glue.join(inner) + ")"
    if kind == "zone":
        return f"{_names(c.get('entity_id'), name)} è in {name(str(c.get('zone', '')))}"
    return "una condizione personalizzata è vera"


def action(a, name: Namer) -> str:
    if isinstance(a, str):
        return "un'azione personalizzata"
    call = a.get("action") or a.get("service")
    if call:
        domain, _, service = str(call).partition(".")
        target = a.get("target") or {}
        who = target.get("entity_id") or a.get("entity_id") or (a.get("data") or {}).get("entity_id")
        if domain == "notify":
            return f"invia la notifica «{str((a.get('data') or {}).get('message', ''))[:60]}»"
        if domain == "scene":
            return f"attiva la scena {_names(who, name)}"
        if domain == "script":
            return f"esegui lo script {name(call) if service == 'turn_on' else service}"
        if who:
            return f"{SERVICES.get(service, service.replace('_', ' '))} {_names(who, name, ' e ')}"
        if target.get("area_id"):
            return f"{SERVICES.get(service, service.replace('_', ' '))} tutto in {', '.join(_list(target['area_id']))}"
        return f"esegui {call}"
    if "delay" in a:
        return f"aspetta {_duration(a['delay'])}"
    if "wait_template" in a or "wait_for_trigger" in a:
        return "aspetta un evento"
    if "scene" in a:
        return f"attiva la scena {name(str(a['scene']))}"
    if "choose" in a:
        return "sceglie tra più casi"
    if "if" in a:
        return "se/altrimenti"
    if "repeat" in a:
        return "ripete alcune azioni"
    if "parallel" in a:
        return "esegue più azioni insieme"
    if "variables" in a:
        return "imposta variabili"
    if "stop" in a:
        return "si ferma"
    return "un'azione personalizzata"


def _section(config: dict, singular: str) -> list:
    return [x for x in _list(config.get(singular + "s", config.get(singular))) if isinstance(x, (dict, str))]


def summary(config: dict, name: Namer) -> dict:
    return {"when": [trigger(t, name) for t in _section(config, "trigger")],
            "only_if": [condition(c, name) for c in _section(config, "condition")],
            "then": [action(a, name) for a in _section(config, "action")]}
