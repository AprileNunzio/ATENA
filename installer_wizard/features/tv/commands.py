import re

from features.tv import targets
from features.tv.m3u import norm
from features.tv.store import tv_store

FACE = {"mode": "face"}
WATCH = re.compile(r"\b(metti|mettimi|guarda|guardare|visualizza|sintonizza|trasmetti|voglio vedere|fammi vedere)\b")
SOFT = re.compile(r"\b(accendi|apri|mostra|mostrami|manda)\b")
TV_WORDS = re.compile(r"\b(canale|canali|tv|televisione|diretta|iptv)\b")
STOP = re.compile(r"\b(spegni|chiudi|ferma|togli)\b.*\b(tv|televisione|canale|diretta)\b")
LIST = re.compile(r"\b(che canali|quali canali|elenco (dei )?canali|lista (dei )?canali)\b")


def default_target(rows: list[dict]) -> dict:
    from features.chat import context
    device = context.device.get()
    mine = next((r for r in rows if r["id"] == f"pc:{device}"), None)
    return mine or next(r for r in rows if r["id"] == "display")


async def answer(text: str) -> tuple[str, dict]:
    flat = norm(text)
    if not tv_store.channels():
        if TV_WORDS.search(flat) and (WATCH.search(flat) or LIST.search(flat)):
            return "Non ho ancora nessun canale: aggiungi una playlist IPTV dal pannello TV.", FACE
        raise LookupError("tv")
    if STOP.search(flat):
        targets.stop_display()
        return "Ho chiuso la TV sullo schermo.", FACE
    if LIST.search(flat):
        favs = [tv_store.channel(c)["name"] for c in tv_store.favorites()[:8]]
        names = favs or [c["name"] for c in tv_store.channels()[:8]]
        return f"Ho {len(tv_store.channels())} canali. Alcuni: {', '.join(names)}.", FACE
    if not (WATCH.search(flat) or (SOFT.search(flat) and TV_WORDS.search(flat))):
        raise LookupError("tv")
    channel = tv_store.find(flat)
    if not channel:
        if TV_WORDS.search(flat):
            return "Non trovo quel canale nelle playlist. Prova a dirmi il nome come compare nell'elenco.", FACE
        raise LookupError("tv")
    rows = await targets.listing()
    target = targets.resolve(flat, rows) or default_target(rows)
    try:
        where = await targets.play(channel, target["id"])
    except targets.TargetError as exc:
        return f"Non riesco ad aprire {channel['name']}: {exc}.", FACE
    return f"Ecco {channel['name']} {where}.", FACE
