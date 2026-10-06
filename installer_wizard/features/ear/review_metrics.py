import difflib
import math
import re
import unicodedata

TOKEN = re.compile(r"[a-zàèéìòù0-9']+", re.I)
WEAK_RMS = 0.02
CLIP_FRACTION = 0.02
WAKE_WINDOW_BEFORE = 3.0
WAKE_WINDOW_AFTER = 1.0
HANDLED_BEFORE = 4.0
HANDLED_AFTER = 2.0
TARGET_RMS = 0.075
LOW_AGREEMENT = 0.6


def plain(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word.lower()) if unicodedata.category(c) != "Mn")


def tokens(text: str) -> list[str]:
    return [plain(t) for t in TOKEN.findall(text or "")]


def agreement(live: str, review: str) -> float:
    a, b = tokens(live), tokens(review)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def window_text(segments: list, start: float, end: float) -> str:
    picked = [s["text"] for s in segments if start <= (s["start"] + s["end"]) / 2 <= end]
    return " ".join(picked).strip()


def compare_transcripts(events: list, segments: list) -> list[dict]:
    rows = []
    for ev in events:
        if ev.get("kind") != "transcript" or not ev.get("text"):
            continue
        end = float(ev["t"])
        start = end - float(ev.get("dur") or 2.0)
        review = window_text(segments, start - 0.8, end + 0.8)
        rows.append({"live": ev["text"], "review": review, "score": round(agreement(ev["text"], review), 3)})
    return rows


def _handled(events: list, start: float, end: float) -> bool:
    return any(ev["kind"] in ("wake", "transcript") and start - HANDLED_BEFORE <= float(ev["t"]) <= end + HANDLED_AFTER
               for ev in events)


def wake_audit(events: list, segments: list, has_wake) -> dict:
    missed = true_wakes = false_instant = 0
    for seg in segments:
        if has_wake(seg["text"]) and not _handled(events, seg["start"], seg["end"]):
            missed += 1
    for ev in events:
        if ev["kind"] != "wake":
            continue
        t = float(ev["t"])
        nearby = window_text(segments, t - WAKE_WINDOW_BEFORE, t + WAKE_WINDOW_AFTER)
        if has_wake(nearby):
            true_wakes += 1
        elif ev.get("source") == "instant":
            false_instant += 1
    return {"missed": missed, "true_wakes": true_wakes, "false_instant": false_instant}


def percentile(values: list, q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def level_report(stats: dict) -> dict:
    speech = float(stats.get("speech_p50") or 0.0)
    noise = float(stats.get("noise") or 0.0)
    snr = 20 * math.log10(max(speech, 1e-6) / max(noise, 1e-6)) if speech else 0.0
    gain = min(80.0, TARGET_RMS / speech) if speech > 1e-5 else 0.0
    return {"speech_p50": round(speech, 4), "noise": round(noise, 4), "snr_db": round(snr, 1),
            "weak": bool(speech and speech < WEAK_RMS), "clipped": float(stats.get("clip_frac") or 0.0) > CLIP_FRACTION,
            "recommended_gain": round(gain, 1)}


def summarize(reviews: list) -> dict:
    if not reviews:
        return {"chunks": 0}
    scores = [r["agreement"] for r in reviews if r.get("agreement") is not None]
    total = {k: sum(int(r.get(k, 0)) for r in reviews) for k in ("missed", "true_wakes", "false_instant", "checked")}
    weak = sum(1 for r in reviews if r.get("weak"))
    clipped = sum(1 for r in reviews if r.get("clipped"))
    snrs = [r["snr_db"] for r in reviews if r.get("snr_db")]
    out = {"chunks": len(reviews), "agreement": round(sum(scores) / len(scores), 3) if scores else None,
           "weak_chunks": weak, "clipped_chunks": clipped, "snr_db": round(sum(snrs) / len(snrs), 1) if snrs else None, **total}
    out["advice"] = advice(out)
    return out


def advice(s: dict) -> list[str]:
    tips = []
    chunks = max(1, s["chunks"])
    if s.get("agreement") is not None and s["agreement"] < LOW_AGREEMENT:
        tips.append("Capisco spesso male le frasi: avvicina il microfono o scegli un modello di ascolto più preciso.")
    if s.get("missed", 0) >= 2:
        tips.append("Ti sento dire «Atena» ma non mi attivo sempre: sto abbassando la soglia di attivazione.")
    if s.get("false_instant", 0) >= 2:
        tips.append("Mi attivo anche quando nessuno mi chiama: sto alzando la soglia di attivazione.")
    if s["weak_chunks"] / chunks >= 0.5:
        tips.append("La voce arriva debole: amplifico di più oppure avvicina il microfono.")
    if s["clipped_chunks"] / chunks >= 0.25:
        tips.append("La voce arriva troppo forte e distorce: riduci il volume d'ingresso del microfono.")
    if s.get("snr_db") is not None and s["snr_db"] < 8:
        tips.append("Il rumore di fondo è alto rispetto alla voce: un microfono più vicino aiuta più dell'amplificazione.")
    return tips
