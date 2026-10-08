import re
import time
import unicodedata

from features.ear.learner import name_variant
from features.people import people

MAX_TEXT = 200
MAX_ITEMS = 40
KINDS = ("wake", "command", "reading")

PLANS = {
    "it": {
        "wake": ["Atena", "Atena", "Atena", "Hey Atena", "Hey Atena", "Ehi Atena"],
        "command": ["Atena, che ore sono?", "Atena, accendi la luce del soggiorno", "Hey Atena, metti un po' di musica",
                    "Atena, ricordami di chiamare la mamma domani alle nove"],
        "reading": ["Buongiorno Atena, oggi è una splendida giornata per imparare qualcosa di nuovo.",
                    "Vorrei sapere che tempo farà domani pomeriggio e se devo portare l'ombrello.",
                    "La mia voce è unica: da oggi mi riconoscerai anche senza guardarmi."],
    },
    "en": {
        "wake": ["Atena", "Atena", "Atena", "Hey Atena", "Hey Atena", "Okay Atena"],
        "command": ["Atena, what time is it?", "Atena, turn on the living room light", "Hey Atena, play some music",
                    "Atena, remind me to call mum tomorrow at nine"],
        "reading": ["Good morning Atena, today is a wonderful day to learn something new.",
                    "I would like to know what the weather will be like tomorrow afternoon.",
                    "My voice is unique: from today you will recognise me even without seeing me."],
    },
    "fr": {
        "wake": ["Atena", "Atena", "Atena", "Hey Atena", "Hey Atena", "Dis Atena"],
        "command": ["Atena, quelle heure est-il ?", "Atena, allume la lumière du salon", "Hey Atena, mets un peu de musique",
                    "Atena, rappelle-moi d'appeler maman demain à neuf heures"],
        "reading": ["Bonjour Atena, aujourd'hui est une belle journée pour apprendre quelque chose de nouveau.",
                    "J'aimerais savoir quel temps il fera demain après-midi.",
                    "Ma voix est unique : à partir d'aujourd'hui tu me reconnaîtras même sans me voir."],
    },
}


def language(lang: str | None) -> str:
    return lang if lang in PLANS else "it"


def plan(lang: str | None) -> list[dict]:
    chosen = PLANS[language(lang)]
    return [{"kind": kind, "text": text} for kind in KINDS for text in chosen[kind]]


def plain(text: str) -> str:
    folded = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in folded if unicodedata.category(c) != "Mn")


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", plain(text))


def similarity(expected: str, heard: str) -> float:
    want, got = set(words(expected)), set(words(heard))
    return len(want & got) / len(want) if want else 0.0


def evaluate(item: dict, heard: str) -> dict:
    kind, said = item["kind"], item["text"]
    heard = " ".join(str(heard or "").split())[:MAX_TEXT]
    variant = name_variant(heard) if kind in ("wake", "command") else None
    if kind == "wake":
        ok = variant is not None
    elif kind == "command":
        ok = variant is not None and similarity(said, heard) >= 0.5
    else:
        ok = bool(heard)
    return {"kind": kind, "said": said, "heard": heard, "ok": ok, "variant": variant}


def _clean_level(level) -> dict:
    level = level if isinstance(level, dict) else {}
    out = {}
    for key in ("rms", "peak", "clipping"):
        try:
            out[key] = round(min(1.0, max(0.0, float(level.get(key, 0)))), 4)
        except (TypeError, ValueError):
            out[key] = 0.0
    advice = level.get("advice")
    out["advice"] = advice if advice in ("ok", "lower", "raise") else "ok"
    return out


def record(slug: str, lang: str | None, answers: list) -> dict:
    profile = people.load(slug)
    if not profile:
        raise LookupError(slug)
    items = plan(lang)
    if not isinstance(answers, list) or not answers or len(answers) > MAX_ITEMS:
        raise ValueError("Risultati dell'addestramento non validi")
    results, levels = [], []
    for answer in answers:
        if not isinstance(answer, dict) or not isinstance(answer.get("index"), int) or not 0 <= answer["index"] < len(items):
            raise ValueError("Risultati dell'addestramento non validi")
        results.append(evaluate(items[answer["index"]], str(answer.get("heard") or "")))
        levels.append(_clean_level(answer.get("level")))
    variants = sorted({r["variant"] for r in results if r["variant"]})
    spoken = [r for r in results if r["kind"] in ("wake", "command")]
    dictionary = [{"said": r["said"], "heard": r["heard"]} for r in spoken if r["heard"] and plain(r["heard"]) != plain(r["said"])]
    profile["voice_training"] = {
        "trained_at": time.time(),
        "language": language(lang),
        "score": round(100 * sum(r["ok"] for r in results) / len(results)),
        "wake_variants": variants,
        "dictionary": dictionary[:MAX_ITEMS],
        "level": {"rms": round(max(lv["rms"] for lv in levels), 4), "peak": round(max(lv["peak"] for lv in levels), 4),
                  "clipping": round(max(lv["clipping"] for lv in levels), 4),
                  "advice": next((lv["advice"] for lv in reversed(levels) if lv["advice"] != "ok"), "ok")},
        "results": results,
    }
    people.save(profile)
    return profile["voice_training"]
