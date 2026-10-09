import os
import re

CODE = re.compile(r"^[a-z]{2,3}$")
MIN_SHARE = 0.6


def allowed(raw: str | None = None) -> list[str]:
    text = os.environ.get("ATENA_EAR_LANGUAGES", "") if raw is None else raw
    return [c for c in (p.strip().lower() for p in text.split(",")) if CODE.match(c)]


def pick(probabilities, home: str, permitted: list[str], min_prob: float) -> str:
    ranked = [(str(lang), float(prob)) for lang, prob in probabilities or []]
    if not ranked:
        return home
    if not permitted:
        lang, prob = max(ranked, key=lambda x: x[1])
        return lang if lang == home or prob >= min_prob else home
    pool = [(lang, prob) for lang, prob in ranked if lang in permitted or lang == home]
    total = sum(prob for _, prob in pool)
    if not pool or total <= 0:
        return home
    lang, prob = max(pool, key=lambda x: x[1])
    return lang if lang == home or prob / total >= MIN_SHARE else home
