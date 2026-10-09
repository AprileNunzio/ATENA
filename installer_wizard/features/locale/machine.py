import asyncio
import json
import logging
import re
import time

from config import STATE_DIR, UI_LANGUAGES, WEB_DIR

log = logging.getLogger("atena.locale")
NATIVE = ("it", "en", "fr")
EXTRA = {k: v for k, v in UI_LANGUAGES.items() if k not in NATIVE}
RTL = {"ar", "he", "fa", "ur"}
BATCH = 40
MAX_RUNS = 3
SLOT = re.compile(r"\{\d+\}")
CATALOG = WEB_DIR / "shared" / "i18n_catalog.json"
CACHE_DIR = STATE_DIR / "i18n"


_SOURCES: dict = {"stamp": 0.0, "rows": []}


def sources() -> list[tuple[str, str]]:
    stamp = CATALOG.stat().st_mtime
    if stamp != _SOURCES["stamp"]:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        pairs = [(it, en) for it, en in data["pairs"]] + [(it, en) for en, it in data["reverse"]]
        _SOURCES.update(stamp=stamp, rows=list(dict.fromkeys(pairs)))
    return _SOURCES["rows"]


def valid(source: str, target) -> bool:
    return isinstance(target, str) and bool(target.strip()) and len(target) < 4 * len(source) + 40 \
        and sorted(SLOT.findall(source)) == sorted(SLOT.findall(target))


class MachineCatalog:
    def __init__(self) -> None:
        self.jobs: dict[str, asyncio.Task] = {}
        self.progress: dict[str, dict] = {}

    @staticmethod
    def _path(lang: str):
        return CACHE_DIR / f"{lang}.json"

    def load(self, lang: str) -> dict[str, str]:
        try:
            data = json.loads(self._path(lang).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except ValueError as exc:
            log.warning("Catalogo %s illeggibile, lo rifaccio: %s", lang, exc)
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}

    def _save(self, lang: str, table: dict[str, str]) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = self._path(lang).with_suffix(".tmp")
        tmp.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path(lang))

    def view(self, lang: str) -> dict:
        if lang not in EXTRA:
            raise KeyError(lang)
        table = self.load(lang)
        rows = sources()
        pairs = [[it, table[it]] for it, _ in rows if it in table]
        pairs += [[en, table[it]] for it, en in rows if it in table and en != it]
        missing = sum(1 for it, _ in rows if it not in table)
        if missing and lang not in self.jobs and self.progress.get(lang, {}).get("runs", 0) < MAX_RUNS:
            self.jobs[lang] = asyncio.get_running_loop().create_task(self._run(lang))
        return {"lang": lang, "pairs": pairs, "done": len(rows) - missing, "total": len(rows), "running": lang in self.jobs,
                "rtl": lang in RTL, "error": self.progress.get(lang, {}).get("error", "")}

    async def _batch(self, lang: str, rows: list[tuple[str, str]]) -> dict[str, str]:
        from features.brain.llm import BrainUnavailable, generate
        listing = "\n".join(json.dumps({"it": it, "en": en}, ensure_ascii=False) for it, en in rows)
        prompt = (f"Translate these user-interface strings of a home assistant app into {EXTRA[lang]} ({lang}). "
                  "Use the Italian text, with English as a hint. Keep placeholders like {0} exactly, keep emoji, symbols, "
                  "product names and punctuation; be short and natural for buttons and labels. Answer only with JSON "
                  f'{{"t": [...]}} containing exactly {len(rows)} strings in the same order.\n\n{listing}')
        try:
            out = await generate(prompt, as_json=True, max_tokens=60 * len(rows) + 200, temperature=0.1, kind="deep",
                                 timeout=300, govern=False)
        except (BrainUnavailable, ValueError) as exc:
            raise RuntimeError(str(exc)[:200]) from exc
        items = (out or {}).get("t") if isinstance(out, dict) else None
        if not isinstance(items, list) or len(items) != len(rows):
            return {}
        return {it: str(t).strip() for (it, _), t in zip(rows, items) if valid(it, t)}

    async def _run(self, lang: str) -> None:
        table = self.load(lang)
        todo = [(it, en) for it, en in sources() if it not in table]
        runs = self.progress.get(lang, {}).get("runs", 0) + 1
        self.progress[lang] = {"started": time.time(), "error": "", "runs": runs}
        try:
            for i in range(0, len(todo), BATCH):
                try:
                    table.update(await self._batch(lang, todo[i:i + BATCH]))
                except RuntimeError as exc:
                    self.progress[lang]["error"] = str(exc)
                    log.warning("Traduzione dell'interfaccia in %s interrotta: %s", lang, exc)
                    break
                self._save(lang, table)
        finally:
            self.jobs.pop(lang, None)


machine = MachineCatalog()
