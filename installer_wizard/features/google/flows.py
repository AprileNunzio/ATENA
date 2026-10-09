import re
import threading
import time
import urllib.parse
from dataclasses import dataclass

from config import ETC_DIR
from sealed import SealedFile

FLOW_TTL = 1800
USED_TTL = 600
_CODE = re.compile(r"(?:^|[?&#\s])code=([^&#\s\"'<>]+)")
_STATE = re.compile(r"(?:^|[?&#\s])state=([^&#\s\"'<>]+)")
_ERROR = re.compile(r"(?:^|[?&#\s])error=([^&#\s\"'<>]+)")
_BARE_CODE = re.compile(r"^4/[0-9A-Za-z_\-]{20,}$")


class LinkError(ValueError):
    pass


@dataclass(frozen=True)
class Pasted:
    code: str
    state: str
    error: str


def parse(text: str) -> Pasted:
    raw = urllib.parse.unquote_plus("".join(str(text or "").split()))[:4000]
    if _BARE_CODE.match(raw):
        return Pasted(raw, "", "")
    found = {name: rx.search(raw) for name, rx in (("code", _CODE), ("state", _STATE), ("error", _ERROR))}
    return Pasted(*(m.group(1) if m else "" for m in (found["code"], found["state"], found["error"])))


class FlowStore:
    def __init__(self, vault: SealedFile) -> None:
        self._vault = vault
        self._lock = threading.Lock()

    def _load(self) -> dict:
        now = time.time()
        data = self._vault.load()
        flows = {k: v for k, v in data.get("flows", {}).items() if now - v.get("at", 0) < FLOW_TTL}
        used = {k: v for k, v in data.get("used", {}).items() if now - v < USED_TTL}
        return {"flows": flows, "used": used}

    def create(self, state: str, slug: str, verifier: str) -> None:
        with self._lock:
            data = self._load()
            data["flows"][state] = {"slug": slug, "verifier": verifier, "at": time.time()}
            self._vault.save(data)

    def pending(self) -> list[dict]:
        with self._lock:
            flows = self._load()["flows"]
        now = time.time()
        return sorted(({"slug": v["slug"], "expires_in": int(FLOW_TTL - (now - v["at"]))} for v in flows.values()),
                      key=lambda f: -f["expires_in"])

    def resolve(self, pasted: Pasted, slug_hint: str = "") -> tuple[str, dict]:
        with self._lock:
            data = self._load()
        flows = data["flows"]
        if pasted.state and pasted.state in flows:
            return pasted.state, flows[pasted.state]
        if pasted.state and pasted.state in data["used"]:
            raise LinkError("Questo indirizzo è già stato usato: l'account risulta collegato, aggiorna la pagina")
        candidates = sorted(((k, v) for k, v in flows.items() if not slug_hint or v["slug"] == slug_hint),
                            key=lambda kv: -kv[1]["at"])
        if candidates and (slug_hint or len({v["slug"] for _, v in candidates}) == 1):
            return candidates[0]
        if not flows:
            raise LinkError("Nessun collegamento in attesa (il link è scaduto dopo 30 minuti o è stato annullato): "
                            "premi di nuovo «Collega» e incolla l'indirizzo finale")
        raise LinkError("Più collegamenti in attesa: incolla l'indirizzo completo, compreso «state=…»")

    def consume(self, state: str) -> None:
        with self._lock:
            data = self._load()
            data["flows"].pop(state, None)
            data["used"][state] = time.time()
            self._vault.save(data)

    def cancel(self, slug: str) -> None:
        with self._lock:
            data = self._load()
            data["flows"] = {k: v for k, v in data["flows"].items() if v["slug"] != slug}
            self._vault.save(data)


flows = FlowStore(SealedFile(ETC_DIR / "google_flows.vault", ETC_DIR / "google.key"))
