import re

from features.understanding.context import Context

MATHS = re.compile(r"\d|\b(?:piu|meno|per|diviso|alla)\b.*\d")
FOLLOW_UP = re.compile(r"\b(?:e adesso|e ora|poi|quindi|invece|ancora|prova con|ora fai|adesso fai|e se|e con)\b")


def whiteboard(ctx: Context) -> float:
    from features.whiteboard import commands as w
    t, on_board, opened = ctx.plain, bool(w.BOARD.search(ctx.plain)), "lavagna" in ctx.widgets
    acts = [w.OPEN, w.CLOSE, w.CLEAR, w.FULL, w.SOLVE, w.EXPLAIN, w.WRITE, w.LOOK, w.UNDO]
    if on_board:
        return 0.97 if any(a.search(t) for a in acts) else 0.8
    if w.COLLAB.search(t) and w.MATH_COLLAB.search(t):
        return 0.95
    if not opened:
        return 0.0
    if (w.SOLVE.search(t) and w.MATH.search(t)) or w.bare_math(t):
        return 0.9
    if w.SOLVE.search(t):
        return 0.88
    if ctx.follows("whiteboard") and (w.MATH.search(t) or FOLLOW_UP.search(t)):
        return 0.85
    if w.UNDO.search(t) or w.EXPLAIN.search(t):
        return 0.75
    if w.FULL.search(t) or w.NORMAL.search(t) or w.WRITE.search(t):
        return 0.7
    return 0.6 if w.LOOK.search(t) else 0.0


def livecam(ctx: Context) -> float:
    from features.cameras import commands as c
    t = ctx.plain
    if c.DEVICE.search(t) and (c.OPEN.search(t) or c.CLOSE.search(t)):
        return 0.95
    if time_pending(c):
        return 0.85
    opened = "live_cam" in ctx.widgets
    if opened and (c.FULL.search(t) or c.NORMAL.search(t)):
        return 0.75
    return 0.55 if ctx.follows("livecam") and c.DEVICE.search(t) else 0.0


def time_pending(module) -> bool:
    import time
    return time.time() < module.pending["until"]


def music(ctx: Context) -> float:
    from features.music import commands as m
    t = ctx.plain
    noun = bool(m.NOUNS.search(t))
    if m.PLAY.match(t) and noun and not re.search(r"\b(?:web\s?cam|telecamera|lavagna|widget|schermo|finestra)\b", t):
        return 0.88
    if m.PLAY.match(t) and re.match(r"^(?:per favore |ti prego |ehi |atena )*(?:suona|riproduci|fai partire|fammi sentire|ascolta|ascoltiamo)\b", t):
        return 0.8
    if m.active_device() and (noun or "volume" in t or len(t.split()) <= 5) and (
            m.PAUSE.search(t) or m.RESUME.search(t) or m.NEXT.search(t) or m.PREVIOUS.search(t) or m.STOPPING.search(t) or "volume" in t):
        return 0.7
    return 0.0


def home(ctx: Context) -> float:
    from features.home_assistant.home import brain
    from features.home_assistant.nlu.parser import parse
    if not brain.catalog.entities:
        return 0.0
    plan = parse(ctx.text, brain.catalog)
    if plan is None:
        return 0.0
    if plan["kind"] == "command":
        return 0.85 if plan.get("how") == "nome" else 0.7
    return {"query": 0.8, "ask": 0.7}.get(plan["kind"], 0.3)


def people(ctx: Context) -> float:
    t = ctx.plain
    if any(k in t for k in ("anni", "compleanno", "nato", "nata", "profilo", "scheda", "lavoro", "appunta", "ricordati", "chi sono")):
        return 0.9
    return 0.0


CLAIMS = {"whiteboard": whiteboard, "livecam": livecam, "music": music, "home": home, "people": people}
DESCRIPTIONS = {
    "whiteboard": "la lavagna condivisa (aprirla, scrivere, calcoli ed equazioni passo passo, spiegazioni, controllare ciò che è scritto)",
    "livecam": "le webcam e telecamere in diretta (aprirle, tutto schermo, chiuderle)",
    "music": "la musica della libreria locale su Chromecast, DLNA e display (suonare, pausa, volume)",
    "home": "i dispositivi di casa (luci, porte, serrature, tapparelle, clima, prese)",
    "people": "la gestione persone e anagrafe (scoprire o ricordare età, quanti anni ho, compleanni, lavoro, gusti, o appuntare e memorizzare dettagli su di sé o su altre persone)",
}


def score_all(ctx: Context) -> dict[str, float]:
    out = {}
    for name, fn in CLAIMS.items():
        try:
            out[name] = fn(ctx)
        except Exception:
            out[name] = 0.0
    return out
