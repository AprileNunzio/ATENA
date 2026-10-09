import re

import httpx
from config import env_get

PROVIDERS = {
    "deepgram": ("https://api.deepgram.com/v1/projects", "token", "DEEPGRAM_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1/models", "bearer", "GROQ_API_KEY"),
    "openai": ("https://api.openai.com/v1/models", "bearer", "OPENAI_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", "query", "GEMINI_API_KEY"),
}
_URL = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~/\-]*)?$")
_KEY = re.compile(r"^[A-Za-z0-9._\-:]{8,300}$")


class KeyCheckError(ValueError):
    pass


def stored_key(provider: str) -> str:
    explicit = env_get("ATENA_ONLINE_STT_KEY", "").strip()
    if explicit:
        return explicit
    spec = PROVIDERS.get(provider)
    return env_get(spec[2], "").strip() if spec else ""


def _request(provider: str, key: str, url: str) -> tuple[str, dict, dict]:
    if provider == "custom":
        if not _URL.match(url) or ".." in url:
            raise KeyCheckError("Indirizzo del server non valido")
        root = url.rstrip("/").removesuffix("/v1/audio/transcriptions").removesuffix("/audio/transcriptions")
        return f"{root}/v1/models", ({"Authorization": f"Bearer {key}"} if key else {}), {}
    if provider not in PROVIDERS:
        raise KeyCheckError("Fornitore sconosciuto")
    if not key:
        raise KeyCheckError("Inserisci la chiave API")
    if not _KEY.match(key):
        raise KeyCheckError("La chiave contiene caratteri non validi")
    endpoint, style, _ = PROVIDERS[provider]
    if style == "query":
        return endpoint, {}, {"key": key}
    return endpoint, {"Authorization": f"{'Token' if style == 'token' else 'Bearer'} {key}"}, {}


async def check(provider: str, key: str = "", url: str = "") -> dict:
    key = key.strip() or stored_key(provider)
    endpoint, headers, params = _request(provider, key, url.strip())
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            res = await client.get(endpoint, headers=headers, params=params)
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"Servizio non raggiungibile ({type(exc).__name__})"}
    if res.status_code in (401, 403):
        return {"ok": False, "message": "Chiave rifiutata dal fornitore: controlla di averla copiata tutta"}
    if res.status_code >= 400:
        return {"ok": False, "message": f"Il fornitore ha risposto con errore {res.status_code}"}
    return {"ok": True, "message": "Chiave valida: il servizio risponde"}
