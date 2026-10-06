import re
import time

import httpx
import licensing
from config import DEMO, ollama_remote, ollama_url, read_env

from features.cloud.catalog import BY_ID, is_cloud, is_server, parse_ref
from features.cloud.vault import vault
from features.brain.roles import FALLBACK_ROLE, ROLES, split_order

CATALOG = [
    {"name": "qwen2.5:7b", "label": "Qwen 2.5 · 7 B", "size_gb": 4.7, "roles": ["deep"], "category": "deep", "rank": 1,
     "notes": "Il modello più votato sul web: eccezionale in italiano, logica, riassunti e compiti complessi."},
    {"name": "deepseek-r1:7b", "label": "DeepSeek R1 · 7 B", "size_gb": 4.7, "roles": ["deep"], "category": "reasoning", "rank": 2,
     "notes": "Il fenomeno mondiale del ragionamento: pensa passo-passo prima di dare la risposta finale."},
    {"name": "llama3.1:8b", "label": "Llama 3.1 · 8 B", "size_gb": 4.9, "roles": ["deep"], "category": "deep", "rank": 3,
     "notes": "Lo standard universale di Meta: affidabile, memoria estesa e versatile per ogni uso quotidiano."},
    {"name": "deepseek-r1:8b", "label": "DeepSeek R1 · 8 B", "size_gb": 4.9, "roles": ["deep"], "category": "reasoning", "rank": 4,
     "notes": "Unione tra la base solida di Llama 3.1 e il potente motore di pensiero analitico di DeepSeek."},
    {"name": "granite3.3:2b", "label": "Granite 3.3 · 2 B", "size_gb": 1.5, "roles": ["chat", "deep"], "category": "chat", "rank": 5,
     "notes": "IBM, licenza Apache-2.0 anche per uso commerciale: veloce, italiano supportato ufficialmente, contesto da 128K."},
    {"name": "qwen2.5:3b", "label": "Qwen 2.5 · 3 B", "size_gb": 1.9, "roles": ["chat", "deep"], "category": "chat", "rank": 5,
     "notes": "Veloce e ottimo in italiano, ma con licenza di sola ricerca: solo uso personale e non commerciale."},
    {"name": "qwen2.5-coder:7b", "label": "Qwen 2.5 Coder · 7 B", "size_gb": 4.7, "roles": ["deep", "coder"], "category": "code", "rank": 6,
     "notes": "Specialista numero uno nel codice: scrive, debugga e spiega Python, JavaScript, HTML e SQL."},
    {"name": "deepseek-r1:14b", "label": "DeepSeek R1 · 14 B", "size_gb": 9.0, "roles": ["deep"], "category": "reasoning", "rank": 7,
     "notes": "Ragionamento profondo di livello avanzato: ideale per problemi complessi di logica e matematica."},
    {"name": "llama3.2:3b", "label": "Llama 3.2 · 3 B", "size_gb": 2.0, "roles": ["chat", "deep"], "category": "chat", "rank": 8,
     "notes": "Nuova generazione Meta per dialoghi fluidi, istruzioni veloci e riassunti immediati."},
    {"name": "qwen2.5:1.5b", "label": "Qwen 2.5 · 1,5 B", "size_gb": 1.0, "roles": ["chat"], "category": "chat", "rank": 9,
     "notes": "Ultra-veloce e leggero: perfetto per il Sistema 1 di Atena e per CPU senza scheda video."},
    {"name": "mistral:7b", "label": "Mistral · 7 B", "size_gb": 4.1, "roles": ["chat", "deep"], "category": "deep", "rank": 10,
     "notes": "Celebre modello europeo: risposte dirette, sintetiche e ad alte prestazioni generali."},
    {"name": "deepseek-r1:1.5b", "label": "DeepSeek R1 · 1,5 B", "size_gb": 1.1, "roles": ["chat", "deep"], "category": "reasoning", "rank": 11,
     "notes": "Ragionamento matematico in formato tascabile: gira agilmente anche su computer portatili base."},
    {"name": "mistral-nemo:12b", "label": "Mistral Nemo · 12 B", "size_gb": 7.1, "roles": ["deep"], "category": "deep", "rank": 12,
     "notes": "Creato con NVIDIA: vocabolario vasto, italiano estremamente naturale e scrittura fluida."},
    {"name": "qwen2.5-coder:14b", "label": "Qwen 2.5 Coder · 14 B", "size_gb": 9.0, "roles": ["deep", "coder"], "category": "code", "rank": 13,
     "notes": "Programmatore senior autonomo: progetta intere applicazioni e risolve problemi algoritmici."},
    {"name": "phi4:14b", "label": "Phi 4 · 14 B", "size_gb": 9.1, "roles": ["deep"], "category": "deep", "rank": 14,
     "notes": "L'eccellenza Microsoft nel ragionamento: addestrato con dati ad alta densità informativa."},
    {"name": "gemma2:9b", "label": "Gemma 2 · 9 B", "size_gb": 5.4, "roles": ["deep"], "category": "deep", "rank": 15,
     "notes": "Modello di punta Google: comprensione testuale ricca, tono cordiale e ottima sintesi."},
    {"name": "llama3.2:1b", "label": "Llama 3.2 · 1 B", "size_gb": 1.3, "roles": ["chat"], "category": "chat", "rank": 16,
     "notes": "Modello compatto di Meta per risposte rapide a basso consumo di memoria."},
    {"name": "phi3.5", "label": "Phi 3.5 mini · 3,8 B", "size_gb": 2.2, "roles": ["deep"], "category": "deep", "rank": 17,
     "notes": "Capacità logiche e di deduzione sopra la media per le sue ridotte dimensioni."},
    {"name": "qwen2.5:0.5b", "label": "Qwen 2.5 · 0,5 B", "size_gb": 0.4, "roles": ["chat"], "category": "chat", "rank": 18,
     "notes": "Il più piccolo in assoluto: tempo di risposta in millisecondi anche su mini-PC."},
    {"name": "gemma2:2b", "label": "Gemma 2 · 2 B", "size_gb": 1.6, "roles": ["chat"], "category": "chat", "rank": 19,
     "notes": "Google compatto: dialoghi piacevoli e veloci con bassissimo carico di sistema."},
    {"name": "llava:7b", "label": "LLaVA · 7 B (Visione)", "size_gb": 4.7, "roles": ["deep"], "category": "vision", "rank": 20,
     "notes": "Intelligenza visiva multimodale: analizza foto, cattura screenshot e descrive scene."},
    {"name": "gemma3:4b", "label": "Gemma 3 · 4 B", "size_gb": 3.3, "roles": ["deep"], "category": "deep", "rank": 21,
     "notes": "Nuova generazione multilingue di Google con eccellente padronanza dell'italiano."},
    {"name": "qwen2.5:14b", "label": "Qwen 2.5 · 14 B", "size_gb": 9.0, "roles": ["deep"], "category": "deep", "rank": 22,
     "notes": "Massima profondità concettuale per schede video con almeno 12-16 GB di VRAM."},
    {"name": "deepseek-r1:32b", "label": "DeepSeek R1 · 32 B", "size_gb": 20.0, "roles": ["deep"], "category": "reasoning", "rank": 23,
     "notes": "Potenza di calcolo eccezionale vicina ai modelli commerciali. Richiede GPU da 24 GB."},
    {"name": "qwen2.5-coder:1.5b", "label": "Qwen 2.5 Coder · 1,5 B", "size_gb": 1.0, "roles": ["coder"], "category": "code", "rank": 24,
     "notes": "Autocompletamento codice leggero ed efficiente per sviluppo locale."},
    {"name": "qwen2.5:32b", "label": "Qwen 2.5 · 32 B", "size_gb": 20.0, "roles": ["deep"], "category": "deep", "rank": 25,
     "notes": "Modello per uso professionale: risposte enciclopediche e ragionamento elaborato."},
    {"name": "gemma3:12b", "label": "Gemma 3 · 12 B", "size_gb": 8.1, "roles": ["deep"], "category": "deep", "rank": 26,
     "notes": "Qualità di analisi elevata e ragionamento esteso per sistemi con GPU generosa."},
    {"name": "llama3.2-vision:11b", "label": "Llama 3.2 Vision · 11 B", "size_gb": 7.9, "roles": ["deep"], "category": "vision", "rank": 29,
     "notes": "Comprensione visiva di Meta per diagrammi, tabelle e foto. Attenzione: la licenza non lo concede a chi risiede nell'UE."},
    {"name": "qwen2.5vl:7b", "label": "Qwen 2.5 VL · 7 B (Visione)", "size_gb": 6.0, "roles": ["deep"], "category": "vision", "rank": 27,
     "notes": "Visione con licenza Apache-2.0: legge documenti, tabelle, grafici e scrittura a mano."},
    {"name": "granite3.3:8b", "label": "Granite 3.3 · 8 B", "size_gb": 4.9, "roles": ["deep"], "category": "deep", "rank": 28,
     "notes": "IBM, Apache-2.0: ragionamento e istruzioni affidabili, italiano supportato, adatto anche alle aziende."},
    {"name": "nomic-embed-text", "label": "Nomic Embed Text", "size_gb": 0.3, "roles": [], "category": "embed", "rank": 29,
     "notes": "Modello di embedding vettoriale per la memoria semantica istantanea a 0ms."},
    {"name": "bge-m3", "label": "BGE-M3 (Embeddings)", "size_gb": 1.2, "roles": [], "category": "embed", "rank": 30,
     "notes": "Embedding multilingue ad alta densità per indicizzazione documenti e memoria profonda."},
]
_BY_NAME = {m["name"]: m for m in CATALOG}

MAX_TOKENS = {r.id: r.max_tokens for r in ROLES}

_DEEP = re.compile(
    r"\b(spiega(mi)?|spiegazione|analizza|analisi|confronta|differenz[ae]|vantaggi|svantaggi|perch[ée]"
    r"|come funziona|in dettaglio|dettagliat\w*|approfondi\w*|passo (a|per) passo|ragiona|dimostra|valuta"
    r"|riassumi|riassunto|traduci|scrivi (un|una|il|la|lo|dei|delle)|componi|progetta|pianifica|organizza"
    r"|strategia|calcola|risolvi|equazion\w*|codice|script|programma|funzione|python|javascript|bash|sql|html|css|json|yaml|regex|query"
    r"|algoritmo|errore|debug|configura|installa|consigli(ami)?|elenca|lista di|pro e contro|storia d\w*)\b",
    re.I)
_CHITCHAT = re.compile(r"^\s*(ciao|buongiorno|buonasera|buonanotte|grazie|ok|okay|va bene|perfetto|come stai"
                       r"|chi sei|sei li|ci sei|salve|hey|ehi)\b", re.I)


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        key = norm(x)
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


def norm(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


class Brains:
    def __init__(self) -> None:
        self._installed: tuple[float, list[str]] = (0.0, [])
        self.stats: dict[str, dict] = {}
        self.last: dict = {}
        self._listeners: list = []

    def on_change(self, callback) -> None:
        self._listeners.append(callback)

    @staticmethod
    def config() -> dict:
        env = read_env()
        main = env.get("ATENA_LLM_MODEL") or "granite3.3:2b"
        fast = env.get("ATENA_LLM_FAST_MODEL") or main
        custom = {r.id: split_order(env.get(r.env_key, "")) for r in ROLES}
        orders = {
            "chat": custom["chat"] or [fast, main],
            "deep": custom["deep"] or [main, fast],
        }
        for role in ROLES:
            orders.setdefault(role.id, custom[role.id] or orders[FALLBACK_ROLE])
        routing = env.get("ATENA_LLM_ROUTING")
        return {
            "routing": routing if routing in ("auto", "1", "0") else "auto",
            "main": main, "fast": fast,
            **{rid: _dedupe(order) for rid, order in orders.items()},
            **{f"{rid}_custom": bool(order) for rid, order in custom.items()},
        }

    async def installed(self) -> list[str]:
        ts, names = self._installed
        if time.time() - ts < 30:
            return names
        if DEMO:
            names = ["granite3.3:2b", "qwen2.5:1.5b", "nomic-embed-text:latest"]
        else:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    names = [m["name"] for m in (await client.get(f"{ollama_url()}/api/tags")).json().get("models", [])]
            except (httpx.HTTPError, ValueError, KeyError):
                return names
        self._installed = (time.time(), names)
        return names

    @staticmethod
    def usable(model: str, installed: set) -> bool:
        if is_cloud(model):
            try:
                provider, _ = parse_ref(model)
            except ValueError:
                return False
            return vault.configured(provider)
        return not installed or norm(model) in installed

    @staticmethod
    def describe(model: str) -> dict:
        if is_cloud(model):
            try:
                provider, name = parse_ref(model)
            except ValueError:
                return {"ref": model, "model": model, "origin": "cloud", "provider": "rimosso", "label": model}
            return {"ref": model, "model": name, "origin": "server" if is_server(provider) else "cloud",
                    "provider": BY_ID[provider].name,
                    "label": f"{name} · {BY_ID[provider].name}"}
        where = ollama_url().split("//", 1)[-1] if ollama_remote() else "Questo server"
        return {"ref": model, "model": model, "origin": "local", "provider": where,
                "label": f"{model} · {where if ollama_remote() else 'locale'}"}

    def active_now(self, kind: str) -> dict | None:
        cfg = self.config()
        installed = {norm(n) for n in self._installed[1]}
        for model in _dedupe(cfg[kind] + cfg["deep" if kind == "chat" else "chat"]):
            if self.usable(model, installed):
                return self.describe(model)
        return None

    def invalidate(self) -> None:
        self._installed = (0.0, [])
        for callback in self._listeners:
            try:
                callback()
            except OSError:
                pass

    @staticmethod
    def classify(text: str) -> tuple[str, str]:
        t = text.strip()
        if _CHITCHAT.match(t) and len(t) < 60:
            return "chat", "saluto o conversazione breve"
        if "```" in t or t.count("\n") >= 3:
            return "deep", "testo strutturato o codice"
        if len(t) > 220:
            return "deep", "richiesta lunga"
        if t.count("?") >= 2:
            return "deep", "più domande insieme"
        m = _DEEP.search(t)
        if m:
            return "deep", f"richiede ragionamento («{m.group(0).lower()}»)"
        if re.search(r"\d+\s*[-+*/^x×÷]\s*\d+", t):
            return "deep", "calcolo"
        return "chat", "conversazione"

    async def route(self, text: str) -> dict:
        cfg, installed = self.config(), {norm(n) for n in await self.installed()}
        routing = cfg["routing"]
        split = routing == "1" or (routing == "auto" and norm(cfg["chat"][0]) != norm(cfg["deep"][0]))
        kind, reason = self.classify(text) if split else ("deep", "cervello unico")
        primary = cfg[kind]
        other = cfg["deep" if kind == "chat" else "chat"]
        chain = [m for m in _dedupe(primary + other) if self.usable(m, installed)]
        if not chain:
            chain = primary[:1]
        return {"kind": kind, "reason": reason, "models": chain, "max_tokens": MAX_TOKENS[kind]}

    def record(self, model: str, ms: float, ok: bool, kind: str) -> None:
        s = self.stats.setdefault(model, {"ok": 0, "fail": 0, "avg_ms": ms})
        s["ok" if ok else "fail"] += 1
        if ok:
            s["avg_ms"] = round(s["avg_ms"] * 0.7 + ms * 0.3)
        self.last = {"model": model, "kind": kind, "ms": round(ms), "at": time.time()}

    @staticmethod
    def fit(size_gb: float | None, hw: dict) -> dict:
        if size_gb is None:
            return {"level": "ok", "label": "installato", "tps": 20.0, "where": "locale"}
        vram, ram = hw.get("vram_gb", 0), hw.get("ram_gb", 8)
        on_gpu = vram and size_gb * 1.2 + 0.5 <= vram
        free_ram = ram - 3.0
        if on_gpu:
            tps, where = 180 / max(size_gb, 0.3), "GPU"
        else:
            tps, where = 14 / max(size_gb, 0.3), "CPU"
        if not on_gpu and size_gb * 1.25 + 0.4 > free_ram:
            return {"level": "no", "label": "troppo grande per questa macchina", "tps": round(tps, 1), "where": where}
        speed = "istantaneo" if tps >= 25 else "veloce" if tps >= 11 else "medio" if tps >= 5 else "lento"
        level = "ok" if tps >= 5 else "slow"
        return {"level": level, "label": f"{speed} (~{tps:.0f} parole/s su {where})", "tps": round(tps, 1), "where": where}

    async def overview(self, hw: dict) -> dict:
        cfg = self.config()
        names = await self.installed()
        installed = {norm(n) for n in names}
        catalog = []
        for m in CATALOG:
            catalog.append({**m, "installed": norm(m["name"]) in installed, "fit": self.fit(m["size_gb"], hw),
                            "license": licensing.describe(licensing.model_license(m["name"]))})
        extra = [n for n in names if norm(n) not in {norm(m["name"]) for m in CATALOG} and "embed" not in n]
        for n in extra:
            catalog.append({"name": n, "label": n, "size_gb": None, "roles": ["chat", "deep"], "category": "other", "rank": 99,
                            "installed": True, "notes": "Installato manualmente", "fit": {"level": "ok", "label": "installato", "where": "locale"},
                            "license": licensing.describe(licensing.model_license(n))})

        def entries(lst):
            return [{"name": n, "installed": norm(n) in installed, "available": self.usable(n, installed),
                     "stats": self.stats.get(norm(n)) or self.stats.get(n), **self.describe(n)} for n in lst]
        auto_fast, auto_main = self.auto_pick(hw)
        roles = [{"id": r.id, "icon": r.icon, "label": r.label, "hint": r.hint,
                  "custom": cfg[f"{r.id}_custom"], "entries": entries(cfg[r.id]),
                  "active": self.active_now(r.id)} for r in ROLES]
        last = {**self.last, **self.describe(self.last["model"])} if self.last.get("model") else {}
        return {"routing": cfg["routing"], "roles": roles, "last_used": last,
                "main": cfg["main"], "fast": cfg["fast"], "suggested": {"chat": auto_fast, "deep": auto_main},
                "catalog": catalog, "last": self.last, "hardware": hw}

    @staticmethod
    def auto_pick(hw: dict) -> tuple[str, str]:
        vram, ram = hw.get("vram_gb", 0), hw.get("ram_gb", 8)
        if vram >= 20:
            deep = "qwen2.5:14b"
        elif vram >= 8 or ram >= 24:
            deep = "qwen2.5:7b"
        elif ram >= 7:
            deep = "granite3.3:2b"
        else:
            deep = "qwen2.5:1.5b"
        if vram >= 6:
            fast = "granite3.3:2b"
        elif ram >= 6:
            fast = "qwen2.5:1.5b"
        else:
            fast = "qwen2.5:0.5b"
        return fast, deep


brains = Brains()
