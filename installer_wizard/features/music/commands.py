import asyncio
import random
import re
import socket
import unicodedata

from config import PUBLIC_PORT
from features.music import catalog, conf, listening, mixes, playlists
from features.music.db import db
from features.music.outputs import outputs

PLAY = re.compile(r"^(?:per favore |ti prego |ehi |atena )*(?:metti(?:mi)?|riproduci|suona|fai partire|fammi sentire|fammi ascoltare|voglio ascoltare|"
                  r"ascoltiamo|ascolta|mandami|play)\b\s*(?P<rest>.*)$")
NOUNS = re.compile(r"\b(musica|canzone|canzoni|brano|brani|album|disco|dischi|playlist|mix|radio|cantante|band|artista)\b")
STOP = {"il", "lo", "la", "le", "i", "gli", "un", "una", "uno", "di", "del", "della", "dello", "dei", "degli", "delle", "da", "dal", "dalla", "po", "qualcosa",
        "canzone", "canzoni", "brano", "brani", "musica", "album", "disco", "dischi", "playlist", "mix", "radio", "cantante", "band", "artista", "per", "favore",
        "mia", "mio", "miei", "mie", "nuova", "nuovo", "ancora", "adesso", "ora", "subito", "tutta", "tutto", "intero", "completo", "che", "mi", "piace"}
TARGET = re.compile(r"\b(?:su|sul|sullo|sulla|sui|in|nel|nella|nello|dal|dalla|sull)\s+(?P<name>[a-z0-9' ]{2,40})$")
PAUSE = re.compile(r"\b(?:metti in pausa|pausa|fermati un attimo|ferma un attimo)\b")
RESUME = re.compile(r"\b(?:riprendi|continua|rimetti|riparti|riavvia)\b")
NEXT = re.compile(r"\b(?:prossim[ao]|salta|avanti|successiv[ao]|cambia)\b")
PREVIOUS = re.compile(r"\b(?:precedente|indietro|torna alla|canzone prima)\b")
STOPPING = re.compile(r"\b(?:ferma|spegni|stoppa|stop|basta)\b")
VOLUME_UP = re.compile(r"\b(?:alza|aumenta|piu forte|sali)\b")
VOLUME_DOWN = re.compile(r"\b(?:abbassa|diminuisci|piu piano|scendi|meno forte)\b")
VOLUME_SET = re.compile(r"\bvolume\b.*?\b(\d{1,3})\s*(?:%|per cento|percento)?")
LIKE = re.compile(r"\b(?:mi piace|aggiungi ai preferiti|salva (?:questa|il brano)|metti il cuore)\b")
USER = "voce"
STEP = 0.15
FACE = {"mode": "face"}


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", str(text or "").lower()).encode("ascii", "ignore").decode()).strip()


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", plain(text))]


def lan_base() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        host = sock.getsockname()[0]
    except OSError:
        host = "127.0.0.1"
    finally:
        sock.close()
    return f"http://{host}" + ("" if PUBLIC_PORT == 80 else f":{PUBLIC_PORT}")


def active_device() -> str | None:
    for device_id, session in outputs.sessions.items():
        if session.state in ("playing", "paused") and device_id in outputs.devices:
            return device_id
    return None


def pick_device(name: str) -> dict | None:
    wanted = set(tokens(name)) - STOP
    if wanted:
        scored = sorted(((len(wanted & set(tokens(d["name"]))), d) for d in outputs.devices.values()), key=lambda x: -x[0])
        if scored and scored[0][0] > 0:
            return scored[0][1]
        return None
    current = active_device()
    if current:
        return outputs.devices[current]
    displays = sorted((d for d in outputs.devices.values() if d["kind"] == "display"), key=lambda d: -d.get("seen", 0))
    if displays:
        return displays[0]
    return next(iter(outputs.devices.values()), None)


def score(query: list[str], text: str) -> float:
    have = set(tokens(text))
    if not query or not have or not set(query) <= have:
        return 0.0
    return len(query) / len(have)


def find_playlist(query: list[str]) -> tuple[float, dict] | None:
    best = None
    for row in db.rows("SELECT id, owner, name FROM playlists"):
        s = score(query, row["name"])
        if s > 0 and (best is None or s > best[0]):
            best = (s, row)
    return best


def best_match(query: list[str], hint: str) -> tuple[str, float, dict] | None:
    found = catalog.search(" ".join(query), 60)
    options = []
    for t in found["tracks"]:
        options.append(("track", score(query, t["title"]) + (0.15 if "canzone" in hint or "brano" in hint else 0), t))
    for a in found["albums"]:
        options.append(("album", score(query, a["album"]) + (0.15 if "album" in hint or "disco" in hint else 0), a))
    for a in found["artists"]:
        options.append(("artist", score(query, a["artist"]) + (0.15 if re.search(r"artista|cantante|band|musica di|canzoni di|brani di", hint) else 0), a))
    options = [o for o in options if o[1] > 0]
    return max(options, key=lambda o: o[1]) if options else None


def artist_tracks(artist_key: str) -> list[dict]:
    rows = catalog.tracks("plays", 120, 0, USER, "artist_key=?", (artist_key,))
    random.shuffle(rows)
    return rows


def resolve(rest: str, hint: str) -> tuple[str, list[dict]] | None:
    query = [w for w in tokens(rest) if w not in STOP]
    if not query:
        liked = mixes.mix("liked", USER) or mixes.mix("random", USER)
        pool = liked or catalog.tracks("random", 40, 0, USER)
        return ("un po' della tua musica", pool) if pool else None
    pl = find_playlist(query)
    match = best_match(query, hint)
    if pl and (not match or pl[0] >= match[1] or "playlist" in hint):
        data = playlists.get(pl[1]["id"], pl[1]["owner"])
        return (f"la playlist {pl[1]['name']}", data["tracks"]) if data and data["tracks"] else None
    if not match:
        genre = next((g["genre"] for g in catalog.genres() if set(query) <= set(tokens(g["genre"]))), None)
        return (f"il genere {genre}", mixes.mix(f"genre:{genre}", USER)) if genre else None
    kind, _, item = match
    if kind == "track":
        return f"«{item['title']}» di {item['artist']}", [item]
    if kind == "album":
        album = catalog.album(item["album_key"], USER)
        return f"l'album {item['album']} di {item['album_artist']}", album["tracks"] if album else []
    return f"i brani di {item['artist']}", artist_tracks(item["artist_key"])


def split_target(text: str) -> tuple[str, str]:
    found = TARGET.search(text)
    if not found:
        return text, ""
    candidate = found.group("name").strip()
    for device in outputs.devices.values():
        if set(tokens(candidate)) & (set(tokens(device["name"])) - STOP):
            return text[:found.start()].strip(), candidate
    return text, ""


async def start(device: dict, label: str, tracks: list[dict]) -> str:
    if not tracks:
        return "Non ho trovato brani da riprodurre."
    ids = [t["id"] for t in tracks[:300]]
    await outputs.start(device["id"], USER, ids, 0, 0, lan_base())
    return f"Ok, metto {label} su {device['name']}."


async def play(text: str) -> tuple[str, dict]:
    match = PLAY.match(text)
    body, target = split_target(match.group("rest"))
    await outputs.refresh(False)
    if not outputs.devices:
        return "Non c'è nessuno schermo o altoparlante collegato per riprodurre la musica. Apri la pagina del display o collega un Chromecast.", FACE
    device = pick_device(target)
    if device is None:
        return f"Non trovo il dispositivo «{target}».", FACE
    found = await asyncio.to_thread(resolve, body, text)
    if found is None:
        if not catalog.stats()["tracks"]:
            return "La libreria musicale è ancora vuota: metti dei brani nella cartella Da smistare.", FACE
        return f"Non trovo «{body.strip() or 'niente'}» nella tua libreria.", FACE
    label, tracks = found
    return await start(device, label, tracks), FACE


async def control(text: str) -> tuple[str, dict]:
    device_id = active_device()
    if device_id is None:
        raise LookupError
    session = outputs.sessions[device_id]
    volume = VOLUME_SET.search(text)
    if volume:
        level = max(0, min(100, int(volume.group(1)))) / 100
        await outputs.control(device_id, "volume", level, lan_base())
        return f"Volume al {int(level * 100)} per cento.", FACE
    if VOLUME_UP.search(text) or VOLUME_DOWN.search(text):
        level = max(0.0, min(1.0, session.volume + (STEP if VOLUME_UP.search(text) else -STEP)))
        await outputs.control(device_id, "volume", level, lan_base())
        return ("Alzo il volume." if VOLUME_UP.search(text) else "Abbasso il volume."), FACE
    if LIKE.search(text) and session.current is not None:
        listening.like(USER, session.current, True)
        return "Fatto, l'ho aggiunta ai preferiti.", FACE
    actions = (("pause", PAUSE, "In pausa."), ("resume", RESUME, "Riprendo."), ("prev", PREVIOUS, "Torno al brano precedente."),
               ("next", NEXT, "Passo al prossimo brano."), ("stop", STOPPING, "Ho fermato la musica."))
    for action, pattern, speech in actions:
        if pattern.search(text):
            await outputs.control(device_id, action, 0.0, lan_base())
            return speech, FACE
    raise LookupError


async def answer(text: str) -> tuple[str, dict]:
    if not conf.voice():
        raise LookupError
    t = plain(text)
    music_noun = bool(NOUNS.search(t))
    if PLAY.match(t) and (music_noun or re.match(r"^(?:per favore |ti prego |ehi |atena )*(?:suona|riproduci|fai partire|fammi sentire|fammi ascoltare|ascoltiamo|ascolta|voglio ascoltare)\b", t)):
        if not re.search(r"\b(?:web\s?cam|telecamera|videocamera|camera|widget|schermo|finestra)\b", t):
            return await play(t)
    if active_device() and (music_noun or "volume" in t or len(t.split()) <= 5):
        return await control(t)
    raise LookupError
