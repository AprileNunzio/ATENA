import logging
import time

from state import store

from features.brain import sight as seeing
from features.brain.llm import BrainUnavailable
from features.cameras import live
from features.desktop.desk import desk
from features.vision import stills

log = logging.getLogger("atena.vision")
PROMPT = ("Descrivi in italiano, in modo completo e concreto, tutto ciò che si vede ora nella foto: le persone (quante, cosa fanno, "
          "abbigliamento, espressione, senza ipotizzare identità), gli oggetti e dove si trovano, eventuali testi leggibili, ambiente e "
          "luce, movimento o situazioni insolite. Rispondi SOLO con JSON: {\"description\": testo di tre-cinque frasi da leggere ad alta "
          "voce, \"objects\": [{\"label\": nome, \"box\": [x, y, larghezza, altezza] normalizzati tra 0 e 1}], \"text\": testi leggibili "
          "oppure stringa vuota}.")
HINT = "Per descrizioni più ricche serve un modello che vede le immagini: aggiungilo nel Cervello (per esempio GPT-4o, Claude, Gemini o llava)."
DARK, DIM, BRIGHT = 45, 85, 205


def join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


def since(stamp: float) -> str:
    seconds = max(0, time.time() - stamp)
    if seconds < 90:
        return "da poco"
    return f"da {int(seconds // 60)} minuti" if seconds < 5400 else f"da {int(seconds // 3600)} ore"


def person_line(p: dict) -> str:
    who = p["name"] if p.get("known") else "una persona che non conosco"
    if p.get("liveness", {}).get("state") == "spoof":
        return "una foto o uno schermo che mostra un volto"
    where = "vicino" if p.get("near") else "lontano"
    look = ", rivolto verso di me" if p.get("facing") else ""
    return f"{who}, {where}{look}, presente {since(p.get('since', time.time()))}"


def people_sentence(people: list[dict]) -> str:
    if not people:
        return "Non vedo nessuna persona."
    lines = [person_line(p) for p in people[:6]]
    head = "Vedo " + ("una persona: " if len(lines) == 1 else f"{len(lines)} persone: ")
    return head + "; ".join(lines) + "."


def objects_sentence(objects: list[dict]) -> tuple[str, list[str]]:
    held = list(dict.fromkeys(o["label"] for o in objects if o.get("held")))
    others = [o["label"] for o in objects if not o.get("held") and o["label"] not in held]
    names = list(dict.fromkeys(others))
    parts = []
    if held:
        parts.append(f"In mano ha {join(held)}")
    if names:
        parts.append(f"Nella stanza noto {join(names[:8])}")
    return (". ".join(parts) + "." if parts else ""), held + names


def brightness(jpeg: bytes) -> float | None:
    try:
        import cv2
        import numpy as np
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    except (ImportError, ValueError):
        return None
    return None if image is None else float(image.mean())


def light_sentence(jpeg: bytes) -> str:
    level = brightness(jpeg)
    if level is None:
        return ""
    if level < DARK:
        return "L'immagine è molto buia."
    if level < DIM:
        return "La stanza è poco illuminata."
    return "La luce è molto forte." if level > BRIGHT else ""


def open_sources() -> list[str]:
    found = []
    for instance in desk.instances.values():
        if instance["id"] == "live_cam":
            found.append((instance.get("data") or {}).get("source", ""))
    return found


def targets(text: str) -> list[dict]:
    rows = live.listing()
    named = live.match(text, rows)
    if len(named) == 1:
        return named
    opened = [r for r in rows if r["id"] in open_sources()]
    if opened:
        return opened
    main = [r for r in rows if r["main"]]
    return main or rows[:1]


async def look(jpeg: bytes) -> tuple[dict, str] | None:
    try:
        data, model = await seeing.look(jpeg, PROMPT, as_json=True, max_tokens=800)
    except BrainUnavailable:
        return None
    except Exception as exc:
        log.warning("Descrizione con il modello non riuscita: %s", exc)
        return None
    return (data, model) if isinstance(data, dict) else None


async def one(row: dict) -> dict:
    jpeg = await live.snapshot_bytes(row)
    if not jpeg:
        return {"row": row, "speech": f"{row['name']}: non riesco a ottenere l'immagine in questo momento.", "items": [], "boxes": [], "jpeg": None}
    sentences, items, boxes = [], [], []
    local = row["main"] and row["kind"] == "local" and (store.presence or {}).get("status") == "ok"
    seen = await look(jpeg)
    if local:
        people = (store.presence or {}).get("people", [])
        sentences.append(people_sentence(people))
        items += [{"label": p["name"] if p.get("known") else "Persona sconosciuta", "value": "vicino" if p.get("near") else "lontano",
                   "status": "ok" if p.get("known") else "warn"} for p in people]
        line, labels = objects_sentence((store.presence or {}).get("objects", []))
        if line and not seen:
            sentences.append(line)
        items += [{"label": label, "value": "oggetto", "status": ""} for label in labels]
    if seen:
        data, model = seen
        sentences.append(str(data.get("description") or "").strip())
        boxes = [{"box": stills.norm_box(o.get("box") or []), "label": str(o.get("label", ""))[:40], "tone": "info"}
                 for o in (data.get("objects") or [])[:10] if isinstance(o, dict)]
        text = str(data.get("text") or "").strip()
        if text:
            sentences.append(f"C'è scritto: {text[:200]}")
        items += [{"label": b["label"], "value": "visto dal modello", "status": ""} for b in boxes if b["box"]]
    elif not local:
        sentences.append("Questa telecamera non ha un riconoscimento locale.")
    light = light_sentence(jpeg)
    if light:
        sentences.append(light)
    if not seen:
        sentences.append(HINT)
    speech = " ".join(s for s in sentences if s)
    return {"row": row, "speech": speech, "items": items, "boxes": [b for b in boxes if b["box"]], "jpeg": jpeg}


async def answer(text: str) -> tuple[str, dict]:
    rows = targets(text)
    if not rows:
        return "Non vedo nessuna webcam o telecamera collegata.", {"mode": "face"}
    results = [await one(row) for row in rows[:3]]
    multi = len(results) > 1
    speech = " ".join((f"{r['row']['name']}: " if multi else "") + r["speech"] for r in results)[:1400]
    shown = set(open_sources())
    if all(r["row"]["id"] in shown for r in results):
        return speech, {"mode": "face"}
    panels = []
    for r in results:
        if r["jpeg"]:
            panels.append({"type": "annotated", "title": r["row"]["name"], "src": stills.url(stills.keep(r["jpeg"])), "boxes": r["boxes"], "caption": ""})
        if r["items"]:
            panels.append({"type": "list", "title": f"{r['row']['name']}: cosa vedo", "items": r["items"][:14]})
    return speech, {"mode": "focus", "title": "Cosa vedo", "subtitle": "Analisi dal vivo", "panels": panels}
