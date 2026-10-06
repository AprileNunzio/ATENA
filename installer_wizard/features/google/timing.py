from datetime import datetime

GRACE_SECONDS = 30.0


def minutes_until(start: datetime, now: datetime) -> float:
    return (start - now).total_seconds() / 60


def upcoming(events: list[dict], now: datetime, grace: float = GRACE_SECONDS) -> list[dict]:
    return [e for e in events if not e.get("all_day") and (e["start"] - now).total_seconds() >= -grace]


def ongoing(events: list[dict], now: datetime) -> list[dict]:
    return [e for e in events if not e.get("all_day") and e["start"] < now]


def when(minutes: float) -> str:
    n = round(minutes)
    if n < 1:
        return "adesso"
    if n < 60:
        return f"tra {n} minut{'o' if n == 1 else 'i'}"
    hours, rest = divmod(n, 60)
    base = f"tra {hours} or{'a' if hours == 1 else 'e'}"
    return base + (f" e {rest} minuti" if rest else "")
