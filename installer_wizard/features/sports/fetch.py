import asyncio
import time

import httpx

ALLOWED_HOSTS = ("https://site.api.espn.com/", "https://api.jolpi.ca/")
_MAX_ENTRIES = 256
_cache: dict[str, tuple[float, dict]] = {}
_locks: dict[str, asyncio.Lock] = {}


class SportsUnavailable(RuntimeError):
    pass


async def get_json(url: str, ttl: float) -> dict:
    if not url.startswith(ALLOWED_HOSTS):
        raise SportsUnavailable("fonte non ammessa")
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    lock = _locks.setdefault(url, asyncio.Lock())
    async with lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        try:
            async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Atena-OS"}, follow_redirects=False) as client:
                res = await client.get(url)
            res.raise_for_status()
            data = res.json()
        except (httpx.HTTPError, ValueError) as exc:
            if hit:
                return hit[1]
            raise SportsUnavailable(f"servizio sportivo non raggiungibile ({type(exc).__name__})") from exc
        if len(_cache) >= _MAX_ENTRIES:
            oldest = min(_cache, key=lambda k: _cache[k][0])
            _cache.pop(oldest)
            if oldest != url and not _locks.get(oldest, lock).locked():
                _locks.pop(oldest, None)
        _cache[url] = (time.time(), data if isinstance(data, dict) else {})
        return _cache[url][1]
