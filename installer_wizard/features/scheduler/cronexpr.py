from datetime import datetime, timedelta

ALIASES = {"@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *", "@weekly": "0 0 * * 0",
           "@daily": "0 0 * * *", "@midnight": "0 0 * * *", "@hourly": "0 * * * *"}
MONTHS = {n: i for i, n in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
WEEKDAYS = {n: i for i, n in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"))}
LIMITS = ((0, 59, {}), (0, 23, {}), (1, 31, {}), (1, 12, MONTHS), (0, 7, WEEKDAYS))
HORIZON_DAYS = 366 * 6


class CronError(ValueError):
    pass


class Cron:

    def __init__(self, minute, hour, dom, month, dow, dom_any: bool, dow_any: bool, text: str) -> None:
        self.minute, self.hour, self.dom, self.month, self.dow = minute, hour, dom, month, dow
        self.dom_any, self.dow_any = dom_any, dow_any
        self.text = text

    def day_ok(self, dt: datetime) -> bool:
        dom = dt.day in self.dom
        dow = (dt.weekday() + 1) % 7 in self.dow
        if not self.dom_any and not self.dow_any:
            return dom or dow
        return dom and dow

    def matches(self, dt: datetime) -> bool:
        return (dt.minute in self.minute and dt.hour in self.hour and dt.month in self.month and self.day_ok(dt))


def _value(token: str, names: dict, lo: int, hi: int) -> int:
    token = token.lower()
    if token in names:
        return names[token]
    if not token.isdigit():
        raise CronError(f"valore non valido «{token}»")
    value = int(token)
    if not lo <= value <= hi:
        raise CronError(f"{value} fuori dall'intervallo {lo}-{hi}")
    return value


def _field(text: str, lo: int, hi: int, names: dict) -> tuple[set, bool]:
    values: set = set()
    for part in text.split(","):
        if not part:
            raise CronError("elenco vuoto")
        body, _, step_text = part.partition("/")
        if step_text and (not step_text.isdigit() or int(step_text) < 1):
            raise CronError(f"passo non valido «{step_text}»")
        step = int(step_text) if step_text else 1
        if body == "*":
            start, end = lo, hi
        elif "-" in body:
            a, _, b = body.partition("-")
            start, end = _value(a, names, lo, hi), _value(b, names, lo, hi)
            if start > end:
                raise CronError(f"intervallo al contrario «{body}»")
        else:
            start = _value(body, names, lo, hi)
            end = hi if step_text else start
        values.update(range(start, end + 1, step))
    return values, text.strip() == "*" or text.startswith("*/")


def parse(expr: str) -> Cron:
    text = str(expr or "").strip().lower()
    text = ALIASES.get(text, text)
    parts = text.split()
    if len(parts) != 5:
        raise CronError("servono 5 campi: minuto ora giorno-del-mese mese giorno-della-settimana")
    fields = []
    for part, (lo, hi, names), label in zip(parts, LIMITS, ("minuto", "ora", "giorno del mese", "mese", "giorno della settimana")):
        try:
            fields.append(_field(part, lo, hi, names))
        except CronError as exc:
            raise CronError(f"{label}: {exc}") from None
    minute, hour, dom, month, dow = (f[0] for f in fields)
    dow = {0 if d == 7 else d for d in dow}
    return Cron(minute, hour, dom, month, dow, fields[2][1], fields[4][1], text)


def build(minute: int, hour: int, weekdays: list | None = None) -> Cron:
    dow = ",".join(str((int(d) + 1) % 7) for d in weekdays) if weekdays else "*"
    return parse(f"{int(minute)} {int(hour)} * * {dow}")


def next_after(cron: Cron, dt: datetime) -> datetime:
    t = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = t + timedelta(days=HORIZON_DAYS)
    while t < limit:
        if t.month not in cron.month:
            t = (t.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
        elif not cron.day_ok(t):
            t = (t + timedelta(days=1)).replace(hour=0, minute=0)
        elif t.hour not in cron.hour:
            t = (t + timedelta(hours=1)).replace(minute=0)
        elif t.minute not in cron.minute:
            t += timedelta(minutes=1)
        else:
            return t
    raise CronError("l'espressione non scatta mai")


def fires_between(cron: Cron, since: datetime, until: datetime, limit: int = 500) -> list[datetime]:
    out: list[datetime] = []
    try:
        t = next_after(cron, since)
        while t <= until and len(out) < limit:
            out.append(t)
            t = next_after(cron, t)
    except CronError:
        return out
    return out
