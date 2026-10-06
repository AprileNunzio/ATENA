import random
from datetime import datetime

POLICIES = ("skip", "run_once", "run_all")


def policy_of(value, default: str) -> str:
    value = str(value or "").strip().lower()
    return value if value in POLICIES else default


def plan(fires: list[datetime], policy: str, grace_s: float, now: datetime, max_runs: int) -> list[datetime]:
    if policy == "skip" or grace_s <= 0:
        return []
    due = [f for f in fires if 0 <= (now - f).total_seconds() <= grace_s]
    if not due:
        return []
    if policy == "run_once":
        return [due[-1]]
    return due[-max(1, max_runs):]


def interval_overdue(last: float, every_s: float, now: float, policy: str, grace_s: float, slack_s: float = 90.0) -> str:
    late = now - last - every_s
    if late < 0:
        return "wait"
    if late <= slack_s:
        return "run"
    if policy == "skip" or grace_s <= 0 or late > grace_s:
        return "reset"
    return "run"


def jitter(max_s: float) -> float:
    return random.uniform(0.0, max_s) if max_s > 0 else 0.0
