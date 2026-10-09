import ipaddress
import json
import logging
import threading
import time
from collections import deque

from config import STATE_DIR

from features.firewall import model
from features.firewall.nft import Block

FIREWALL_DIR = STATE_DIR / "firewall"
CONFIG_FILE = FIREWALL_DIR / "config.json"
HISTORY = 20
log = logging.getLogger("atena.firewall")


class FirewallStore:

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.policy = model.Policy()
        self.rules: dict[str, model.Rule] = {}
        self.sets: dict[str, list[model.Address]] = {}
        self.blocks: dict[str, Block] = {}
        self.history: deque[dict] = deque(maxlen=HISTORY)
        self.load()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "policy": self.policy.export(),
                "rules": [r.export() for r in sorted(self.rules.values(), key=lambda r: (r.priority, r.id))],
                "sets": {name: [model.text_of(a) for a in entries] for name, entries in sorted(self.sets.items())},
                "blocks": [{"address": model.text_of(b.address), "expires": b.expires, "reason": b.reason}
                           for b in self.blocks.values()],
            }

    def restore(self, data: dict) -> None:
        policy = model.policy(data.get("policy") or {}, model.Policy())
        rules = {r.id: r for r in (model.rule(item) for item in data.get("rules") or [])}
        sets = {name: model.address_set(name, entries) for name, entries in (data.get("sets") or {}).items()}
        blocks = {}
        for item in data.get("blocks") or []:
            address = model.address(item["address"])
            blocks[address.value] = Block(address, float(item.get("expires") or 0.0), model.comment(item.get("reason", "")))
        with self.lock:
            self.policy, self.rules, self.sets, self.blocks = policy, rules, sets, blocks

    def load(self) -> None:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.error("Configurazione del firewall illeggibile, resto in monitoraggio: %s", exc)
            return
        try:
            self.restore(data)
        except (KeyError, TypeError, ValueError) as exc:
            log.error("Configurazione del firewall non valida, resto in monitoraggio: %s", exc)

    def save(self) -> None:
        with self.lock:
            FIREWALL_DIR.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(CONFIG_FILE)

    def checkpoint(self, reason: str) -> None:
        with self.lock:
            self.history.append({"at": time.time(), "reason": reason[:120], "state": self.snapshot()})

    def rollback(self) -> dict | None:
        with self.lock:
            if not self.history:
                return None
            entry = self.history.pop()
            self.restore(entry["state"])
            self.save()
            return entry

    def prune(self, now: float | None = None) -> int:
        now = now or time.time()
        with self.lock:
            expired = [k for k, b in self.blocks.items() if b.expires and b.expires <= now]
            for key in expired:
                del self.blocks[key]
            gone = [k for k, r in self.rules.items() if r.expires and r.expires <= now]
            for key in gone:
                del self.rules[key]
            return len(expired) + len(gone)

    def trusted(self, address: model.Address) -> bool:
        with self.lock:
            for t in self.policy.trusted:
                if t.family == "mac" and address.family == "mac" and t.value == address.value:
                    return True
                if t.family in ("ip4", "ip6") and address.family == t.family:
                    if ipaddress.ip_network(address.value, strict=False).subnet_of(ipaddress.ip_network(t.value, strict=False)):
                        return True
        return False


store = FirewallStore()
