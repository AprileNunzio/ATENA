WATCH_SECONDS = 15 * 60
MIN_SAMPLES = 4
MAX_FAILURE = 0.5
FINISHED = ("done", "failed")


def should_rollback(outcomes: list[tuple[float, str]], published_at: float, now: float) -> bool:
    if now - published_at > WATCH_SECONDS:
        return False
    window = [state for started, state in outcomes
              if published_at <= started <= published_at + WATCH_SECONDS and state in FINISHED]
    if len(window) < MIN_SAMPLES:
        return False
    return window.count("failed") / len(window) >= MAX_FAILURE


def compare(first: dict[str, str], second: dict[str, str]) -> list[str]:
    return sorted(node for node in set(first) | set(second) if first.get(node) != second.get(node))
