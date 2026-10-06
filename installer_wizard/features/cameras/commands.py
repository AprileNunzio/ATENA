import re
import time

from features.cameras import live
from features.desktop.desk import desk

OPEN = re.compile(r"\b(apri|aprimi|mostra|mostrami|fammi vedere|fai vedere|visualizza|accendi|attiva|avvia|metti|guarda|vediamo)\b")
DEVICE = re.compile(r"\b(web\s?cam|telecamera|telecamere|videocamera|videocamere|camera|cam)\b")
CLOSE = re.compile(r"\b(chiudi|spegni|disattiva|nascondi|togli|ferma|elimina)\b")
FULL = re.compile(r"\b(a )?(tutto|pieno) schermo\b|\bschermo intero\b|\bmassimizza\b|\bingrandisci\b|\bfullscreen\b")
NORMAL = re.compile(r"\b(esci|uscire|torna|tornare|riduci|rimpicciolisci|ripristina)\b.*\b(schermo|dimension\w+|normale|piccol\w+)\b|\bschermo normale\b|\brimpicciolisci\b")
ALL = re.compile(r"\b(tutte|tutti|ogni)\b")
FACE = {"mode": "face"}
pending = {"until": 0.0}


def open_keys() -> dict[str, str]:
    return {k: (i.get("data") or {}).get("name", "") for k, i in desk.instances.items() if i["id"] == "live_cam"}


def open_source(row: dict, full: bool) -> str:
    key = f"live:{row['id']}"
    desk.show("live_cam", {"source": row["id"], "name": row["name"]}, key=key, priority=75)
    if full:
        desk.fullscreen(key, True)
    return key


def pick(text: str, rows: list[dict]) -> list[dict]:
    return live.match(text, rows)


def ask(rows: list[dict]) -> tuple[str, dict]:
    pending["until"] = time.time() + 45
    names = ", ".join(r["name"] for r in rows)
    return f"Quale vuoi vedere? Ho: {names}.", FACE


def opening(text: str, full: bool) -> tuple[str, dict]:
    rows = live.listing()
    if not rows:
        return "Non vedo nessuna webcam o telecamera collegata.", FACE
    if ALL.search(text) and len(rows) > 1:
        for row in rows[:4]:
            open_source(row, False)
        return f"Ecco {min(4, len(rows))} telecamere in diretta.", FACE
    named = pick(text, rows)
    if len(rows) == 1:
        target = rows[0]
    elif len(named) == 1:
        target = named[0]
    else:
        return ask(rows if not named else named)
    pending["until"] = 0.0
    open_source(target, full)
    return f"Ecco {target['name']}{' a tutto schermo' if full else ''}.", FACE


def fullscreen(text: str, on: bool) -> tuple[str, dict]:
    keys = open_keys()
    target = None
    if keys:
        named = pick(text, [{"id": k, "name": n, "kind": "local", "ir": False} for k, n in keys.items()])
        target = named[0]["id"] if len(named) == 1 else next(iter(keys))
    if on and target is None:
        target = desk.fullscreen(None, True)
        if target is None:
            raise LookupError
        return "Ecco, a tutto schermo.", FACE
    if target is None and not on:
        if desk.fullscreen(None, False) is None:
            raise LookupError
        return "Ho riportato il widget alla dimensione normale.", FACE
    desk.fullscreen(target, on)
    return ("Ecco, a tutto schermo." if on else "Ho riportato il widget alla dimensione normale."), FACE


def closing(text: str) -> tuple[str, dict]:
    keys = open_keys()
    if not keys:
        raise LookupError
    named = pick(text, [{"id": k, "name": n, "kind": "local", "ir": False} for k, n in keys.items()])
    chosen = [named[0]["id"]] if len(named) == 1 and not ALL.search(text) else list(keys)
    for key in chosen:
        desk.hide(key=key)
    label = keys[chosen[0]] if len(chosen) == 1 else "le telecamere"
    return f"Ho chiuso {label}.", FACE


async def answer(text: str) -> tuple[str, dict]:
    t = live.plain(text)
    wants_open = bool(OPEN.search(t) and DEVICE.search(t))
    full = bool(FULL.search(t))
    if wants_open:
        return opening(t, full)
    if CLOSE.search(t) and DEVICE.search(t):
        return closing(t)
    if NORMAL.search(t):
        return fullscreen(t, False)
    if full:
        return fullscreen(t, True)
    if time.time() < pending["until"] and not OPEN.search(t) and not CLOSE.search(t):
        rows = live.listing()
        named = pick(t, rows)
        if len(named) == 1:
            return opening(t, False)
        if named:
            return ask(named)
    raise LookupError
