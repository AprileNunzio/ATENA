import logging
import re
import time

import httpx

log = logging.getLogger("atena.rpa")
REPOSITORY = "AprileNunzio/ATENA"
API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=20"
INSTALLER = "ATENA_Assistente_Setup.exe"
CACHE_SECONDS = 3600
TAG_RE = re.compile(r"assistant-v(\d+(?:\.\d+){1,3})")
_cache: dict = {"at": 0.0, "url": ""}


def pick(releases: list) -> str:
    best: tuple = ()
    for release in releases:
        match = TAG_RE.fullmatch(str(release.get("tag_name", "")))
        if not match or release.get("draft") or release.get("prerelease"):
            continue
        url = next((a.get("browser_download_url", "") for a in release.get("assets") or [] if a.get("name") == INSTALLER), "")
        key = tuple(int(n) for n in match.group(1).split("."))
        if url and (not best or key > best[0]):
            best = (key, url)
    return best[1] if best else ""


async def installer_url() -> str:
    if time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["url"]
    try:
        async with httpx.AsyncClient(timeout=10, headers={"Accept": "application/vnd.github+json"}) as client:
            response = await client.get(API)
        response.raise_for_status()
        url = pick(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Release dell'Assistente Windows non leggibili da GitHub: %s", exc)
        return _cache["url"]
    _cache.update(at=time.time(), url=url)
    return url
