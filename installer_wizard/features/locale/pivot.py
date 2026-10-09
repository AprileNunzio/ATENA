import logging
from collections import OrderedDict

from features.voices import languages

PIVOT = "it"
CACHE_SIZE = 256
MAX_CHARS = 1200
log = logging.getLogger("atena.locale")

TO_PIVOT = ("Traduci in italiano la richiesta dell'utente, mantenendo nomi propri, numeri, orari e unità. "
            "Rispondi solo con la traduzione, senza virgolette né commenti.")
FROM_PIVOT = ("Translate the assistant reply into {name}. Keep names, numbers, units, code blocks and line breaks unchanged. "
              "Answer only with the translation, no quotes or comments.")


class Pivot:
    PIVOT = PIVOT

    def __init__(self) -> None:
        self.cache: OrderedDict[tuple[str, str, str], str] = OrderedDict()

    def _remember(self, key: tuple[str, str, str], value: str) -> str:
        self.cache[key] = value
        self.cache.move_to_end(key)
        while len(self.cache) > CACHE_SIZE:
            self.cache.popitem(last=False)
        return value

    async def _translate(self, text: str, system: str, key: tuple[str, str, str]) -> str:
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        from features.brain.llm import BrainUnavailable, generate
        try:
            out = await generate(text[:MAX_CHARS], kind="chat", max_tokens=400, temperature=0.0, system=system,
                                 timeout=20, govern=False)
        except (BrainUnavailable, ValueError) as exc:
            log.warning("Traduzione non disponibile: %s", exc)
            return text
        out = str(out or "").strip().strip('"«»').strip()
        return self._remember(key, out) if out else text

    async def to_pivot(self, text: str, lang: str) -> str:
        if languages.base(lang) in ("", PIVOT) or not text.strip():
            return text
        return await self._translate(text, TO_PIVOT, ("in", lang, text))

    async def from_pivot(self, text: str, lang: str, force: bool = False) -> str:
        target = languages.base(lang)
        if target in ("", PIVOT) or not text.strip():
            return text
        if not force and languages.detect(text, target) == target:
            return text
        name = languages.LANGS.get(target, (target, target, ()))[1]
        return await self._translate(text, FROM_PIVOT.format(name=name), ("out", target, text))


pivot = Pivot()
