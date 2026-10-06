import time
from functools import partial

from features.agent.registry import tool
from features.cameras import captures, events, live, options, unified

cameras = partial(tool, agent="cameras")


def pick(name: str, rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("nessuna webcam o telecamera collegata")
    named = live.match(name, rows) if name else []
    if len(rows) == 1:
        return rows[0]
    if len(named) == 1:
        return named[0]
    raise ValueError("indica quale: " + ", ".join(r["name"] for r in (named or rows)))


def photo_taken(args: dict, result: str) -> str | None:
    row = pick(str(args.get("name", "")), live.listing())
    recent = captures.photos(row["id"])
    return None if recent and time.time() - recent[0]["at"] < 30 else "la foto non risulta salvata"


def motion_set(args: dict, result: str) -> str | None:
    row = pick(str(args.get("name", "")), live.listing())
    wanted = str(args.get("on", "true")).lower() != "false"
    return None if options.get(row["id"])["motion"] == wanted else "l'impostazione del movimento non è cambiata"


@cameras("camera_overview", "riepilogo di webcam e telecamere: tipo, stanza, registrazione, rilevamento del movimento, spazio occupato", {})
async def camera_overview() -> str:
    rows = unified.overview()["sources"]
    if not rows:
        return "nessuna webcam o telecamera collegata"
    lines = []
    for r in rows:
        flags = [r["kind"], *(["registra"] if r["record"]["recording"] else []), *(["movimento attivo"] if r["options"]["motion"] else []),
                 *([f"stanza {r['options']['room']}"] if r["options"]["room"] else [])]
        lines.append(f"- {r['name']} ({', '.join(flags)}); foto salvate: {r['usage']['photos']}, clip: {r['usage']['clips']}")
    return "\n".join(lines)


@cameras("camera_photo", "scatta e salva una foto da una webcam o telecamera", {"name": "nome della telecamera (vuoto se ce n'è una sola)"}, verify=photo_taken)
async def camera_photo(name: str = "") -> str:
    row = pick(name, live.listing())
    photo = await captures.take(row)
    return f"foto salvata da {row['name']} ({photo['name']})"


@cameras("camera_motion", "attiva o disattiva l'avviso di movimento di una telecamera", {"name": "nome della telecamera", "on": "true per attivare, false per spegnere"},
         verify=motion_set)
async def camera_motion(name: str = "", on="true") -> str:
    row = pick(name, live.listing())
    state = str(on).lower() != "false"
    options.put(row["id"], {"motion": state})
    return f"avviso di movimento {'attivato' if state else 'disattivato'} su {row['name']}"


@cameras("camera_events", "ultimi eventi delle telecamere (movimento rilevato)", {"limit": "quanti eventi (default 10)"})
async def camera_events(limit=10) -> str:
    rows = events.recent(max(1, min(50, int(limit or 10))))
    return "\n".join(f"- {time.strftime('%d/%m %H:%M', time.localtime(e['at']))} {e['text']}" for e in rows) or "nessun evento recente"
