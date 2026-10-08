import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import wave
import numpy as np

log = logging.getLogger("atena.ear.online")

RATE = 16000
CUSTOM_URL_RE = re.compile(r"https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]{0,200})?")
TIMEOUT = 4.0
CUSTOM_TIMEOUT = 15.0


def audio_to_wav_bytes(audio: np.ndarray, rate: int = RATE) -> bytes:
    """Converte un array numpy float32 o int16 in un buffer WAV in memoria."""
    buf = io.BytesIO()
    if audio.dtype != np.int16:
        scaled = np.clip(audio, -1.0, 1.0) * 32767.0
        pcm16 = scaled.astype(np.int16)
    else:
        pcm16 = audio

    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()


def custom_endpoint() -> str:
    url = os.environ.get("ATENA_ONLINE_STT_URL", "").strip().rstrip("/")
    if not CUSTOM_URL_RE.fullmatch(url) or ".." in url:
        if url:
            log.warning("Indirizzo del server di trascrizione personalizzato non valido: %s", url[:120])
        return ""
    return url if url.endswith("/audio/transcriptions") else url + "/v1/audio/transcriptions"


def _get_api_key(provider: str) -> str:
    explicit = os.environ.get("ATENA_ONLINE_STT_KEY", "").strip()
    if explicit:
        return explicit

    if provider == "deepgram":
        return os.environ.get("DEEPGRAM_API_KEY", "").strip()
    elif provider == "groq":
        return os.environ.get("GROQ_API_KEY", "").strip()
    elif provider == "openai":
        return os.environ.get("OPENAI_API_KEY", "").strip()
    elif provider == "gemini":
        return os.environ.get("GEMINI_API_KEY", "").strip()
    return ""


def transcribe_deepgram(wav_bytes: bytes, lang: str = "it", api_key: str = "") -> str | None:
    if not api_key:
        return None
    url = f"https://api.deepgram.com/v1/listen?model=nova-2&language={lang}&smart_format=true&punctuate=true"
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/wav",
    }
    req = urllib.request.Request(url, data=wav_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            channels = data.get("results", {}).get("channels", [])
            if channels and channels[0].get("alternatives"):
                transcript = channels[0]["alternatives"][0].get("transcript", "").strip()
                return transcript
    except Exception as exc:
        log.warning("Errore trascrizione online Deepgram: %s", exc)
    return None


def transcribe_openai_compatible(wav_bytes: bytes, endpoint: str, model: str, api_key: str, lang: str = "it",
                                 timeout: float = TIMEOUT) -> str | None:
    boundary = f"----WebKitFormBoundary{int(time.time() * 1000)}"
    body = bytearray()

    # Form field: model
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n".encode("utf-8"))
    # Form field: language
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n{lang}\r\n".encode("utf-8"))
    # Form field: prompt
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"prompt\"\r\n\r\nEhi, Atena.\r\n".encode("utf-8"))
    # File field: file
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode("utf-8"))
    body.extend(wav_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        endpoint,
        data=bytes(body),
        headers={
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return str(data.get("text", "")).strip()
    except Exception as exc:
        log.warning("Errore trascrizione online (%s): %s", model, exc)
    return None


def transcribe_gemini(wav_bytes: bytes, api_key: str) -> str | None:
    if not api_key:
        return None
    import base64
    b64_audio = base64.b64encode(wav_bytes).decode("ascii")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": "Trascrivi esattamente e parola per parola cosa viene detto in questo audio italiano. Restituisci SOLO ed ESCLUSIVAMENTE la trascrizione letterale, senza commenti né virgolette."},
                {"inline_data": {"mime_type": "audio/wav", "data": b64_audio}}
            ]
        }],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 100}
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            candidates = res.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return str(parts[0].get("text", "")).strip()
    except Exception as exc:
        log.warning("Errore trascrizione online Gemini: %s", exc)
    return None


def transcribe_online(audio: np.ndarray, lang: str = "it") -> str | None:
    """Tenta la trascrizione online usando il provider configurato. Ritorna None se fallisce o disattivato."""
    provider = os.environ.get("ATENA_ONLINE_STT_PROVIDER", "deepgram").strip().lower()
    api_key = _get_api_key(provider)
    if provider == "custom":
        endpoint = custom_endpoint()
        if not endpoint:
            return None
        model = os.environ.get("ATENA_ONLINE_STT_MODEL", "").strip() or "whisper-1"
        return transcribe_openai_compatible(audio_to_wav_bytes(audio, RATE), endpoint, model, api_key, lang, CUSTOM_TIMEOUT)
    if not api_key:
        return None

    try:
        wav = audio_to_wav_bytes(audio, RATE)
        if provider == "deepgram":
            return transcribe_deepgram(wav, lang, api_key)
        elif provider == "groq":
            return transcribe_openai_compatible(wav, "https://api.groq.com/openai/v1/audio/transcriptions", "whisper-large-v3-turbo", api_key, lang)
        elif provider == "openai":
            return transcribe_openai_compatible(wav, "https://api.openai.com/v1/audio/transcriptions", "whisper-1", api_key, lang)
        elif provider == "gemini":
            return transcribe_gemini(wav, api_key)
    except Exception as exc:
        log.error("Eccezione durante la trascrizione online: %s", exc)
    return None
