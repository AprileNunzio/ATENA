import base64
import hashlib
import hmac
import ipaddress
import re
import urllib.parse

import httpx

from features.music import tokens

PLAYLIST_LIMIT = 2 * 1024 * 1024
TOKEN_TTL = 12 * 3600
HEADERS = {"User-Agent": "VLC/3.0"}
CORS = {"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"}
_URI_ATTR = re.compile(r'URI="([^"]+)"')
HLS_TYPES = ("mpegurl", "x-mpegurl", "vnd.apple.mpegurl")


class RelayError(RuntimeError):
    pass


def token_for(cid: str) -> str:
    return tokens.sign("tv", cid, TOKEN_TTL)


def valid(cid: str, token: str) -> bool:
    return tokens.verify("tv", cid, token)


def _sig(cid: str, url: str) -> str:
    return hmac.new(tokens.secret(), f"seg|{cid}|{url}".encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def encode(cid: str, url: str, token: str) -> str:
    packed = base64.urlsafe_b64encode(url.encode("utf-8")).decode().rstrip("=")
    return f"/api/tv/seg/{cid}?u={packed}&s={_sig(cid, url)}&t={urllib.parse.quote(token)}"


def decode(cid: str, packed: str, sig: str) -> str:
    try:
        url = base64.urlsafe_b64decode(packed + "=" * (-len(packed) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise RelayError("Segmento non valido") from exc
    if not hmac.compare_digest(_sig(cid, url), str(sig)):
        raise RelayError("Segmento non firmato")
    return url


def internal(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host in ("localhost",) or host.endswith((".local", ".internal", ".lan")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def allowed(origin: str, url: str) -> bool:
    scheme = urllib.parse.urlsplit(url).scheme
    return scheme in ("http", "https") and (not internal(url) or internal(origin))


def is_playlist(url: str, content_type: str) -> bool:
    path = urllib.parse.urlsplit(url).path.lower()
    return path.endswith((".m3u8", ".m3u")) or any(t in content_type.lower() for t in HLS_TYPES)


def rewrite(text: str, base: str, cid: str, token: str, origin: str) -> str:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            def swap(m):
                target = urllib.parse.urljoin(base, m.group(1))
                return f'URI="{encode(cid, target, token)}"' if allowed(origin, target) else 'URI=""'
            out.append(_URI_ATTR.sub(swap, line))
        elif stripped:
            target = urllib.parse.urljoin(base, stripped)
            out.append(encode(cid, target, token) if allowed(origin, target) else "#rimosso")
        else:
            out.append(line)
    return "\n".join(out) + "\n"


_RANGE = re.compile(r"^bytes=\d{0,15}-\d{0,15}$")
PASS_HEADERS = ("content-range", "content-length", "accept-ranges", "content-encoding")


def range_header(value: str | None) -> dict:
    return {"Range": value} if value and _RANGE.match(value) else {}


async def open_upstream(url: str, extra: dict | None = None) -> tuple[httpx.AsyncClient, httpx.Response]:
    client = httpx.AsyncClient(timeout=httpx.Timeout(20, read=30), follow_redirects=True, headers=HEADERS)
    try:
        res = await client.send(client.build_request("GET", url, headers=extra or {}), stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise RelayError(f"sorgente non raggiungibile ({type(exc).__name__})") from exc
    if res.status_code >= 400:
        await res.aclose()
        await client.aclose()
        raise RelayError(f"la sorgente ha risposto {res.status_code}")
    return client, res


async def read_playlist(res: httpx.Response) -> str:
    chunks, size = [], 0
    async for chunk in res.aiter_bytes():
        size += len(chunk)
        if size > PLAYLIST_LIMIT:
            raise RelayError("playlist del canale troppo grande")
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")
