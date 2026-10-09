import ipaddress
import json
import re
import time
from urllib.parse import urlsplit

import httpx

from config import env_get

LOCAL_URL = "http://127.0.0.1:3900"
PROFILE_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
VOICE_PREFIX = "studio_"
MAX_AUDIO = 25 * 1024 * 1024
SPEECH_TIMEOUT = 180
LIST_TTL = 30


class StudioError(RuntimeError):
    pass


def safe_url(raw: str) -> str:
    url = str(raw or "").strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise StudioError("indirizzo non valido: usa per esempio http://192.168.1.20:3900")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise StudioError("l'indirizzo deve contenere solo computer e porta")
    host = parts.hostname
    try:
        ip = ipaddress.ip_address(host)
        if not (ip.is_private or ip.is_loopback or ip.is_link_local):
            raise StudioError("per sicurezza lo Studio delle voci deve essere nella rete di casa")
    except ValueError:
        if "." in host and not host.endswith((".local", ".lan", ".home", ".internal", ".ts.net")):
            raise StudioError("per sicurezza lo Studio delle voci deve essere nella rete di casa")
    return f"{parts.scheme}://{parts.netloc}"


def voice_id(profile_id: str) -> str:
    return VOICE_PREFIX + profile_id


def profile_of(voice: str) -> str:
    pid = str(voice or "").removeprefix(VOICE_PREFIX)
    if not str(voice or "").startswith(VOICE_PREFIX) or not PROFILE_RE.match(pid):
        raise StudioError("voce dello Studio non valida")
    return pid


def _message(res: httpx.Response) -> str:
    try:
        body = res.json()
        detail = body.get("detail") or body.get("error") or body
        if isinstance(detail, dict):
            detail = detail.get("message") or json.dumps(detail)[:200]
        return str(detail)[:200]
    except ValueError:
        return res.text[:200]


class Client:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport
        self.cached: list[dict] = []
        self.cached_at = 0.0
        self.last_error = ""

    @staticmethod
    def enabled() -> bool:
        return env_get("ATENA_VOICESTUDIO", "0") == "1"

    @staticmethod
    def remote() -> bool:
        return env_get("ATENA_VOICESTUDIO_WHERE", "local") == "remote"

    def base(self) -> str:
        return safe_url(env_get("ATENA_VOICESTUDIO_URL", "")) if self.remote() else LOCAL_URL

    @staticmethod
    def headers(key: str | None = None) -> dict:
        token = env_get("ATENA_VOICESTUDIO_KEY", "") if key is None else key
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def _call(self, method: str, path: str, base: str | None = None, key: str | None = None,
                    timeout: float = 15, **kw) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=self.transport) as client:
                res = await client.request(method, (base or self.base()) + path, headers=self.headers(key), **kw)
        except httpx.HTTPError as exc:
            self.last_error = "non raggiungibile"
            raise StudioError(f"lo Studio delle voci non risponde ({type(exc).__name__})") from exc
        if res.status_code in (401, 403):
            self.last_error = "chiave rifiutata"
            raise StudioError("la chiave dello Studio delle voci non è giusta")
        if res.status_code >= 400:
            raise StudioError(_message(res))
        self.last_error = ""
        return res

    async def check(self, url: str | None = None, key: str | None = None) -> dict:
        base = safe_url(url) if url else self.base()
        caps = (await self._call("GET", "/.well-known/voicestudio-speech", base=base, key=key, timeout=8)).json()
        await self._call("GET", "/v1/audio/voices", base=base, key=key, timeout=8)
        return {"ok": True, "protocol": str(caps.get("protocol", ""))[:40]}

    async def voices(self, fresh: bool = False) -> list[dict]:
        if not fresh and time.time() - self.cached_at < LIST_TTL:
            return self.cached
        data = (await self._call("GET", "/v1/audio/voices")).json()
        rows = [{"id": voice_id(v["voice_id"]), "profile": v["voice_id"], "name": str(v.get("name") or v["voice_id"])[:60],
                 "language": str(v.get("language") or "Auto")[:20]}
                for v in data.get("voices", []) if v.get("type") == "profile" and PROFILE_RE.match(str(v.get("voice_id", "")))]
        self.cached, self.cached_at = rows, time.time()
        return rows

    def name_of(self, voice: str) -> str:
        return next((v["name"] for v in self.cached if v["id"] == voice), voice.removeprefix(VOICE_PREFIX))

    async def speech(self, text: str, voice: str, speed: float = 1.0, lang: str | None = None) -> bytes:
        body = {"model": "omnivoice", "input": str(text)[:4000], "voice": profile_of(voice), "response_format": "wav",
                "speed": max(0.5, min(2.0, float(speed or 1.0)))}
        if lang:
            body["language"] = lang
        res = await self._call("POST", "/v1/audio/speech", json=body, timeout=SPEECH_TIMEOUT)
        if not res.content:
            raise StudioError("nessun audio ricevuto")
        return res.content

    async def transcribe(self, name: str, data: bytes, lang: str | None = None) -> str:
        if len(data) > MAX_AUDIO:
            raise StudioError("file audio troppo grande (massimo 25 MB)")
        form = {"model": "whisper-1", "response_format": "json", **({"language": lang} if lang else {})}
        res = await self._call("POST", "/v1/audio/transcriptions", files={"file": (name, data)}, data=form, timeout=600)
        return str(res.json().get("text", "")).strip()

    async def describe(self, description: str) -> dict:
        res = await self._call("POST", "/design/describe", json={"description": str(description)[:500]})
        return res.json()

    async def design(self, name: str, description: str, language: str) -> dict:
        parsed = await self.describe(description)
        attrs = parsed.get("attrs") or {}
        if not any(v != "Auto" for v in attrs.values()):
            raise StudioError("non ho capito che voce vuoi: scegli almeno una caratteristica")
        res = await self._call("POST", "/profiles", data={"name": name, "kind": "design", "language": language,
                                                          "vd_states": json.dumps(attrs)}, timeout=SPEECH_TIMEOUT)
        self.cached_at = 0.0
        return res.json()

    async def clone(self, name: str, audio: bytes, filename: str, sentence: str, language: str) -> dict:
        if len(audio) > MAX_AUDIO:
            raise StudioError("registrazione troppo grande")
        res = await self._call("POST", "/profiles", data={"name": name, "kind": "clone", "language": language,
                                                          "ref_text": sentence},
                               files={"ref_audio": (filename, audio)}, timeout=SPEECH_TIMEOUT)
        profile = res.json()
        await self._call("POST", f"/profiles/{profile_of(voice_id(profile['id']))}/consent",
                         data={"consent_text": sentence}, files={"consent_audio": (filename, audio)})
        self.cached_at = 0.0
        return profile

    async def delete(self, voice: str) -> None:
        await self._call("DELETE", f"/profiles/{profile_of(voice)}")
        self.cached_at = 0.0


client = Client()
