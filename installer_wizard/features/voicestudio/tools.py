import io
import re
import wave

from features.agent.paths import resolve
from features.agent.readers import text_of
from features.agent.registry import tool
from features.shares import archive
from features.voices import catalog
from features.voicestudio.client import MAX_AUDIO, client

CHUNK = 900
MAX_CHUNKS = 60
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}


def chunks(text: str) -> list[str]:
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?…])\s+|\n{2,}", re.sub(r"[ \t]+", " ", str(text))):
        sentence = sentence.strip()
        if not sentence:
            continue
        while len(sentence) > CHUNK:
            parts.append(sentence[:CHUNK])
            sentence = sentence[CHUNK:]
        if len(current) + len(sentence) + 1 > CHUNK and current:
            parts.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def join_wavs(pieces: list[bytes]) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as target:
        for i, piece in enumerate(pieces):
            with wave.open(io.BytesIO(piece), "rb") as src:
                if i == 0:
                    target.setparams(src.getparams())
                target.writeframes(src.readframes(src.getnframes()))
    return out.getvalue()


def _voice(raw: str) -> str:
    voice = str(raw or "").strip()
    if voice:
        found = next((v["id"] for v in client.cached if voice in (v["id"], v["profile"]) or v["name"].lower() == voice.lower()), "")
        if not found:
            raise ValueError(f"nello Studio non c'è una voce chiamata {voice}")
        return found
    main = catalog.voice_name()
    if catalog.is_studio(main):
        return main
    if not client.cached:
        raise ValueError("nello Studio delle voci non c'è ancora nessuna voce: creala dal pannello")
    return client.cached[0]["id"]


@tool("studio_voices", "elenca le voci create nello Studio delle voci (copiate o inventate)", {}, agent="voicestudio")
async def studio_voices() -> str:
    rows = await client.voices(fresh=True)
    main = catalog.voice_name()
    return "\n".join(f"- {v['name']} ({v['id']}){' ← voce di Atena' if v['id'] == main else ''}" for v in rows) \
        or "nessuna voce nello Studio"


@tool("transcribe_audio", "trascrive in testo un file audio o video (riunioni, messaggi vocali, video) in oltre 600 lingue",
      {"path": "file audio o video", "language": "codice lingua facoltativo (it, en…)"}, agent="voicestudio")
async def transcribe_audio(path: str, language: str = "") -> str:
    p = resolve(path)
    if not p.is_file() or p.suffix.lower() not in AUDIO_EXT:
        return f"{p} non è un file audio o video: cercalo prima con find_files"
    if p.stat().st_size > MAX_AUDIO:
        return f"{p.name} è troppo grande (massimo 25 MB)"
    text = await client.transcribe(p.name, p.read_bytes(), str(language or "")[:5] or None)
    return text or "nessuna parola riconosciuta"


@tool("speak_to_file", "legge ad alta voce un testo o un documento con una voce dello Studio e salva l'audio (audiolibro, "
      "messaggio, lettura) nella cartella condivisa", {"text": "testo da leggere (oppure vuoto)", "path": "documento da leggere "
      "(oppure vuoto)", "voice": "nome della voce (vuoto = voce di Atena)", "name": "nome del file"}, agent="voicestudio")
async def speak_to_file(text: str = "", path: str = "", voice: str = "", name: str = "lettura") -> str:
    await client.voices()
    if path:
        source = resolve(path)
        if not source.is_file():
            return f"{source} non esiste: cercalo prima con find_files"
        text = await text_of(source)
    parts = chunks(text)
    if not parts:
        return "non c'è niente da leggere"
    if len(parts) > MAX_CHUNKS:
        return f"il testo è troppo lungo ({len(parts)} parti, massimo {MAX_CHUNKS}): dividilo in capitoli"
    chosen = _voice(voice)
    audio = join_wavs([await client.speech(part, chosen) for part in parts])
    target = archive.new_path("documenti", f"{name}.wav", "lettura")
    target.write_bytes(audio)
    return f"audio salvato in {target} con la voce {client.name_of(chosen)} ({len(parts)} parti)"


@tool("studio_design_voice", "inventa una nuova voce nello Studio a partire da una descrizione in inglese (es. female, elderly, "
      "low pitch)", {"name": "nome della voce", "description": "caratteristiche in inglese"}, agent="voicestudio")
async def studio_design_voice(name: str, description: str, language: str = "it") -> str:
    profile = await client.design(str(name)[:40], str(description)[:300], str(language or "it")[:2])
    return f"voce «{name}» creata nello Studio (id studio_{profile.get('id')})"
