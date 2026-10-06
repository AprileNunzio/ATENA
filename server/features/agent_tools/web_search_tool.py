import html
import logging
import os
import re

import httpx

from server.core.agent_registry.tool_registry import atena_tool

logger = logging.getLogger("atena.web_search_tool")

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
WIKIPEDIA_URL = "https://{lang}.wikipedia.org/w/api.php"
USER_AGENT = "AtenaOS/4 (+https://github.com/AprileNunzio/ATENA)"
TIMEOUT = 12.0
MAX_RESULTS = 10
TAGS = re.compile(r"<[^>]+>")
WIKIPEDIA_NOTICE = "Testi da Wikipedia, licenza CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)."


def _limit(max_results: int) -> int:
    try:
        return max(1, min(MAX_RESULTS, int(max_results)))
    except (TypeError, ValueError):
        return 5


async def _brave(client: httpx.AsyncClient, key: str, query: str, count: int) -> list[str]:
    response = await client.get(BRAVE_URL, params={"q": query, "count": count, "search_lang": "it"},
                                headers={"X-Subscription-Token": key, "Accept": "application/json"})
    response.raise_for_status()
    items = (response.json().get("web") or {}).get("results") or []
    return [f"Titolo: {i.get('title', '')}\nLink: {i.get('url', '')}\nSnippet: {i.get('description', '')}" for i in items[:count]]


async def _wikipedia(client: httpx.AsyncClient, query: str, count: int, lang: str) -> list[str]:
    params = {"action": "query", "list": "search", "srsearch": query, "srlimit": count, "format": "json", "utf8": 1}
    response = await client.get(WIKIPEDIA_URL.format(lang=lang), params=params)
    response.raise_for_status()
    items = (response.json().get("query") or {}).get("search") or []
    return [f"Titolo: {i.get('title', '')}\nLink: https://{lang}.wikipedia.org/wiki/{str(i.get('title', '')).replace(' ', '_')}\n"
            f"Snippet: {html.unescape(TAGS.sub('', str(i.get('snippet', ''))))}" for i in items]


@atena_tool(
    "web_search",
    "Cerca informazioni su internet tramite API ufficiali (Brave Search se configurato, altrimenti Wikipedia). "
    "Usa per prezzi, orari, recensioni, notizie o voci enciclopediche."
)
async def web_search(query: str, max_results: int = 5) -> str:
    count = _limit(max_results)
    key = os.environ.get("ATENA_BRAVE_API_KEY", "").strip()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=False) as client:
            if key:
                results, notice = await _brave(client, key, query, count), "Fonte: Brave Search API."
            else:
                results = await _wikipedia(client, query, count, "it") or await _wikipedia(client, query, count, "en")
                notice = WIKIPEDIA_NOTICE
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Errore nella ricerca web: %s", exc)
        return f"Impossibile completare la ricerca web: {exc}"
    if not results:
        return f"Nessun risultato trovato per la ricerca '{query}'."
    return "Risultati Web:\n\n" + "\n---\n".join(results) + f"\n\n{notice}"
