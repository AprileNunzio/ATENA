import hashlib
import hmac
import os
import secrets
import time

from config import STATE_DIR

SECRET_FILE = STATE_DIR / "music_secret"
DEFAULT_TTL = 6 * 3600
_secret: list = []


def secret() -> bytes:
    if not _secret:
        try:
            value = SECRET_FILE.read_bytes()
        except OSError:
            value = b""
        if len(value) < 32:
            value = secrets.token_bytes(48)
            SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
            SECRET_FILE.write_bytes(value)
            try:
                os.chmod(SECRET_FILE, 0o600)
            except OSError:
                pass
        _secret.append(value)
    return _secret[0]


def mac(kind: str, ref: str, expires: int) -> str:
    return hmac.new(secret(), f"{kind}|{ref}|{expires}".encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def sign(kind: str, ref, ttl: float = DEFAULT_TTL) -> str:
    expires = int(time.time() + ttl)
    return f"{expires}.{mac(kind, str(ref), expires)}"


def verify(kind: str, ref, token: str) -> bool:
    try:
        stamp, given = str(token).split(".", 1)
        expires = int(stamp)
    except ValueError:
        return False
    return expires >= time.time() and hmac.compare_digest(mac(kind, str(ref), expires), given)
