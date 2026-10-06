import re
from datetime import datetime, timedelta

KINDS = (
    ("flight", re.compile(r"\b(volo|aeroporto|flight|airport|imbarco)\b", re.I), "ATENA_MAPS_BUFFER_FLIGHT", 120.0),
    ("train", re.compile(r"\b(treno|stazione|trenitalia|italo|frecciarossa|frecciargento|intercity|binario)\b", re.I),
     "ATENA_MAPS_BUFFER_TRAIN", 10.0),
    ("bus", re.compile(r"\b(pullman|autobus|bus|flixbus|marozzi|autostazione|corriera|terminal|fermata)\b", re.I),
     "ATENA_MAPS_BUFFER_BUS", 15.0),
)
LABELS = {"flight": "il volo", "train": "il treno", "bus": "il pullman"}
MIN_SAMPLES = 5
PRIOR_SHARE = 0.2
SPREAD_SHARE = 0.05
MAX_MARGIN_SHARE = 0.6


def classify(title: str, where: str) -> str | None:
    text = f"{title} {where}"
    for kind, rx, _, _ in KINDS:
        if rx.search(text):
            return kind
    return None


def buffer_minutes(kind: str | None, env) -> float:
    key, default = next(((k, d) for name, _, k, d in KINDS if name == kind), ("ATENA_MAPS_BUFFER_EVENT", 5.0))
    try:
        return max(0.0, min(300.0, float(env(key, str(default)))))
    except ValueError:
        return default


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = q * (len(ordered) - 1)
    low = int(pos)
    high = min(len(ordered) - 1, low + 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def wise_margin(samples: list[float], duration: float, minimum: float, wise: bool = True) -> dict:
    if not wise:
        return {"margin": minimum, "typical": None, "samples": len(samples), "basis": "fisso"}
    if len(samples) < MIN_SAMPLES:
        margin = max(minimum, PRIOR_SHARE * duration)
        return {"margin": round(margin, 1), "typical": None, "samples": len(samples), "basis": "prudenza"}
    spread = percentile(samples, 0.9) - percentile(samples, 0.5)
    margin = min(MAX_MARGIN_SHARE * duration, max(minimum, spread + SPREAD_SHARE * duration))
    typical = (round(percentile(samples, 0.1)), round(percentile(samples, 0.9)))
    return {"margin": round(margin, 1), "typical": typical, "samples": len(samples), "basis": "storico"}


def plan(start: datetime, now: datetime, duration: float, buffer: float, margin: float) -> dict:
    leave = start - timedelta(minutes=duration + buffer + margin)
    arrive_now = now + timedelta(minutes=duration)
    return {"leave": leave, "arrive_if_now": arrive_now, "will_miss": arrive_now > start,
            "tight": arrive_now > start - timedelta(minutes=buffer), "late": leave < now}


def fmt_minutes(minutes: float) -> str:
    m = max(1, round(minutes))
    if m < 60:
        return f"{m} minut{'o' if m == 1 else 'i'}"
    hours, rest = divmod(m, 60)
    return f"{hours} or{'a' if hours == 1 else 'e'}" + (f" e {rest} minuti" if rest else "")


def traffic_note(delay: float | None, live: bool) -> str:
    if not live or delay is None:
        return " (stima senza dati sul traffico)"
    if delay >= 3:
        return f", di cui {round(delay)} per il traffico di adesso"
    return ", senza traffico significativo"


def speech(stage: str, title: str, kind: str | None, start: datetime, now: datetime, duration: float, delay: float | None,
           live: bool, buffer: float, margin: dict, p: dict) -> str:
    what = LABELS.get(kind or "", f"«{title}»")
    if stage == "go":
        return (f"È ora di uscire per {what}: con il traffico di adesso servono {fmt_minutes(duration)} "
                f"e la partenza è alle {start:%H:%M}.")
    head = "Aggiornamento sul traffico. " if stage == "update" else ""
    typical = f"; di solito tra {margin['typical'][0]} e {margin['typical'][1]} minuti" if margin.get("typical") else ""
    text = (f"{head}Per {what} delle {start:%H:%M}: da casa ci vogliono {fmt_minutes(duration)}"
            f"{traffic_note(delay, live)}{typical}.")
    if kind:
        text += f" Conviene arrivare {fmt_minutes(buffer)} prima"
        text += f" e tenere {fmt_minutes(margin['margin'])} di margine" if margin["margin"] >= 1 else ""
    else:
        text += f" Tenga {fmt_minutes(margin['margin'])} di margine" if margin["margin"] >= 1 else ""
    if p["will_miss"]:
        return text + f". Anche partendo subito arriverebbe verso le {p['arrive_if_now']:%H:%M}, dopo l'orario: è molto probabile che lo perda."
    if p["late"]:
        return text + f". L'orario per uscire era le {p['leave']:%H:%M}: parta subito."
    return text + f": parta entro le {p['leave']:%H:%M}."
