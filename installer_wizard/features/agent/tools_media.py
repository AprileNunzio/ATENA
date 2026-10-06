from functools import partial

from features.agent import verify_media
from features.agent.registry import tool
from features.cameras import commands as camera_commands
from features.cameras import live
from features.desktop.desk import desk
from features.music import catalog, commands, conf
from features.music.outputs import outputs
from features.team.board import board

music = partial(tool, agent="music")
cameras = partial(tool, agent="cameras")
ACTIONS = {"pause": "in pausa", "resume": "ripresa", "next": "brano successivo", "prev": "brano precedente", "stop": "fermata", "volume": "volume"}


def _ready() -> None:
    if not conf.voice():
        raise PermissionError("il controllo vocale della musica è disattivato nelle impostazioni")


@music("music_outputs", "elenca gli schermi e gli altoparlanti di rete su cui far suonare la musica (Chromecast, DLNA, display Atena)", {})
async def music_outputs() -> str:
    rows = await outputs.refresh(True)
    if not rows:
        return "nessun dispositivo: apri la pagina del display o collega un Chromecast"
    return "\n".join(f"- {r['name']} ({r['kind']}){' [in riproduzione]' if r['active'] else ''}" for r in rows)


@music("music_search", "cerca brani, album e artisti nella libreria musicale locale", {"query": "titolo, album o artista"})
async def music_search(query: str) -> str:
    found = catalog.search(query, 12)
    lines = [f"brano: {t['title']} — {t['artist']} ({t['album']})" for t in found["tracks"][:8]]
    lines += [f"album: {a['album']} — {a['album_artist']}" for a in found["albums"][:4]]
    lines += [f"artista: {a['artist']}" for a in found["artists"][:4]]
    return "\n".join(lines) or "nessun risultato nella libreria"


@music("music_play", "avvia la musica della libreria su un dispositivo: brano, album, artista, playlist, genere oppure un po' di tutto se la richiesta è vuota",
      {"query": "cosa suonare (vuoto = la mia musica)", "device": "nome del dispositivo (vuoto = quello già attivo o il display)"}, verify=verify_media.playing)
async def music_play(query: str = "", device: str = "") -> str:
    _ready()
    await outputs.refresh(False)
    if not outputs.devices:
        raise ValueError("nessun dispositivo di riproduzione disponibile")
    target = commands.pick_device(device)
    if target is None:
        raise ValueError(f"dispositivo «{device}» non trovato")
    found = commands.resolve(query, query)
    if found is None:
        raise ValueError(f"«{query or 'niente'}» non è nella libreria")
    holder = board.claim("music", f"audio:{target['id']}")
    if holder:
        raise ValueError(f"l'audio di {target['name']} è occupato dall'agente {holder}, che ha la precedenza")
    return await commands.start(target, *found)


@music("music_control", "controlla la musica in corso: pause, resume, next, prev, stop oppure volume (value da 0 a 100)",
      {"action": "pause|resume|next|prev|stop|volume", "value": "percentuale del volume"}, verify=verify_media.controlled)
async def music_control(action: str, value: float = 0) -> str:
    _ready()
    if action not in ACTIONS:
        raise ValueError("azione non valida")
    device_id = commands.active_device()
    if device_id is None:
        raise ValueError("nessuna riproduzione in corso")
    level = max(0.0, min(100.0, float(value))) / 100 if action == "volume" else 0.0
    await outputs.control(device_id, action, level, commands.lan_base())
    return f"{ACTIONS[action]}" + (f" al {int(level * 100)}%" if action == "volume" else "")


@music("music_now", "dice che cosa sta suonando ora e su quale dispositivo", {})
async def music_now() -> str:
    device_id = commands.active_device()
    if device_id is None:
        return "non sta suonando nulla"
    view = outputs.view(outputs.sessions[device_id])
    track = view["track"] or {}
    return f"{track.get('title', '?')} — {track.get('artist', '?')} su {outputs.devices[device_id]['name']} ({view['state']}, brano {view['index'] + 1} di {view['length']})"


@cameras("list_cameras", "elenca le webcam e le telecamere IP collegate e quelle già aperte in diretta", {})
async def list_cameras() -> str:
    rows = live.listing()
    opened = camera_commands.open_keys().values()
    return "\n".join(f"- {r['name']} ({r['kind']}){' [aperta]' if r['name'] in opened else ''}" for r in rows) or "nessuna webcam o telecamera collegata"


@cameras("open_camera", "apre il widget con la visione in diretta di una webcam o telecamera, anche a tutto schermo",
      {"name": "nome della telecamera (vuoto se ce n'è una sola)", "fullscreen": "true per il tutto schermo"}, verify=verify_media.camera_opened)
async def open_camera(name: str = "", fullscreen=False) -> str:
    rows = live.listing()
    if not rows:
        raise ValueError("nessuna webcam o telecamera collegata")
    named = live.match(name, rows) if name else []
    if len(rows) == 1:
        target = rows[0]
    elif len(named) == 1:
        target = named[0]
    else:
        raise ValueError("indica quale: " + ", ".join(r["name"] for r in (named or rows)))
    camera_commands.open_source(target, str(fullscreen).lower() == "true")
    return f"{target['name']} aperta in diretta"


@cameras("close_camera", "chiude i widget delle telecamere in diretta", {"name": "nome (vuoto = tutte)"}, verify=verify_media.camera_closed)
async def close_camera(name: str = "") -> str:
    keys = camera_commands.open_keys()
    if not keys:
        return "nessuna telecamera aperta"
    rows = [{"id": k, "name": n, "kind": "local", "ir": False} for k, n in keys.items()]
    named = live.match(name, rows) if name else rows
    for row in named or rows:
        desk.hide(key=row["id"])
    return "telecamere chiuse"
