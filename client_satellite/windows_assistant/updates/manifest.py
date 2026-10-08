import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PUBLIC_KEY = "DN6SKGGnjtJbKYc7I4CajVCrV8X1hLrXYDR0U9x5qOU="
REPOSITORY = "AprileNunzio/ATENA"
DOWNLOAD_RE = re.compile(rf"https://github\.com/{re.escape(REPOSITORY)}/releases/download/assistant-v[0-9.]+/[A-Za-z0-9_.-]+\.exe")
VERSION_RE = re.compile(r"\d+(?:\.\d+){1,3}")
MAX_SIZE = 400 * 1024 * 1024


class UpdateRejected(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str
    size: int


def version_key(text: str) -> tuple[int, ...]:
    if not VERSION_RE.fullmatch(text or ""):
        raise UpdateRejected(f"versione non valida: {text!r}")
    return tuple(int(part) for part in text.split("."))


def newer(candidate: str, current: str) -> bool:
    return version_key(candidate) > version_key(current)


def verify(manifest: bytes, signature: bytes, public_key: str = PUBLIC_KEY) -> Release:
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key)).verify(base64.b64decode(signature.strip()), manifest)
    except (InvalidSignature, binascii.Error, ValueError) as exc:
        raise UpdateRejected("firma dell'aggiornamento non valida") from exc
    try:
        data = json.loads(manifest.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UpdateRejected("manifesto dell'aggiornamento illeggibile") from exc
    if not isinstance(data, dict):
        raise UpdateRejected("manifesto dell'aggiornamento non valido")
    version, url, digest, size = (data.get(k) for k in ("version", "url", "sha256", "size"))
    version_key(str(version))
    if not isinstance(url, str) or not DOWNLOAD_RE.fullmatch(url):
        raise UpdateRejected("indirizzo di download non autorizzato")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise UpdateRejected("impronta SHA-256 non valida")
    if not isinstance(size, int) or not 0 < size <= MAX_SIZE:
        raise UpdateRejected("dimensione dell'aggiornamento non valida")
    return Release(str(version), url, digest, size)


def check_file(data: bytes, release: Release) -> None:
    if len(data) != release.size:
        raise UpdateRejected("dimensione del file scaricato diversa da quella firmata")
    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), release.sha256):
        raise UpdateRejected("il file scaricato non corrisponde all'impronta firmata")
