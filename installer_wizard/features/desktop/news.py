import html
import logging
import re
import time
import xml.etree.ElementTree as ET

import httpx

from config import env_get

log = logging.getLogger("atena.news")

DEFAULT_FEED = "https://www.ansa.it/sito/notizie/topnews/topnews_rss.xml"
ALLOWED_PREFIXES = ("https://www.ansa.it/", "https://www.repubblica.it/", "https://www.ilsole24ore.com/",
                    "https://feeds.bbci.co.uk/", "https://www.rainews.it/")
MAX_BYTES = 512 * 1024
FRESH_FOR = 15 * 60
RETRY_AFTER = 5 * 60
TAG_RE = re.compile(r"<[^>]+>")
MEDIA = "{http://search.yahoo.com/mrss/}"


def plain(raw: str, limit: int) -> str:
    return " ".join(html.unescape(TAG_RE.sub(" ", str(raw or ""))).split())[:limit]


def https(url: str) -> str:
    url = str(url or "").strip()
    return url[:500] if url.startswith("https://") and " " not in url else ""


def image_of(item) -> str:
    for tag in ("enclosure", f"{MEDIA}content", f"{MEDIA}thumbnail"):
        node = item.find(tag)
        if node is not None and https(node.get("url", "")) and node.get("type", "image").startswith("image"):
            return https(node.get("url"))
    return ""


class News:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.fetched_at = 0.0
        self.failed_at = 0.0

    @staticmethod
    def feed() -> str:
        url = str(env_get("ATENA_NEWS_FEED", DEFAULT_FEED) or "").strip()
        return url if url.startswith(ALLOWED_PREFIXES) else DEFAULT_FEED

    @staticmethod
    def parse(raw: bytes, limit: int = 8) -> list[dict]:
        if b"<!DOCTYPE" in raw[:2048] or b"<!ENTITY" in raw:
            raise ValueError("feed con DTD non ammesso")
        root = ET.fromstring(raw)
        items, seen = [], set()
        for item in root.iter("item"):
            title = plain(item.findtext("title"), 160)
            if not title or title in seen:
                continue
            seen.add(title)
            items.append({"title": title, "text": plain(item.findtext("description"), 1500),
                          "link": https(item.findtext("link")), "image": image_of(item),
                          "at": plain(item.findtext("pubDate"), 40)})
            if len(items) >= limit:
                break
        return items

    async def headlines(self) -> list[dict]:
        now = time.time()
        if now - self.fetched_at < FRESH_FOR or now - self.failed_at < RETRY_AFTER:
            return self.items
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False, headers={"User-Agent": "Atena-OS"}) as client:
                res = await client.get(self.feed())
            res.raise_for_status()
            self.items = self.parse(res.content[:MAX_BYTES])
            self.fetched_at = now
        except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
            self.failed_at = now
            log.warning("Notizie non disponibili: %s", exc)
        return self.items


news = News()
