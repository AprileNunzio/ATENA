import asyncio
import json
import logging
import sys
import time
from collections import deque
from pathlib import Path

from config import env_get
from state import store as system_store

from features.firewall import model
from features.firewall.nft import Block
from features.firewall.store import store

SOCKET = Path("/run/atena/netguard.sock")
SEVERITY = {name: rank for rank, name in enumerate(model.SEVERITIES)}
KINDS = {"port_scan", "host_sweep", "syn_flood", "brute_force", "arp_spoof", "dns_tunnel", "icmp_flood", "exfiltration"}
MAX_LINE = 1 << 20
log = logging.getLogger("atena.firewall")


def _protected() -> set[str]:
    import tls
    addresses = set(tls.local_addresses()) | {"127.0.0.1", "::1"}
    gateway = env_get("ATENA_GATEWAY_IP", "")
    if gateway:
        addresses.add(gateway)
    return addresses


def clean_alert(raw: dict) -> dict | None:
    if not isinstance(raw, dict) or raw.get("kind") not in KINDS or raw.get("severity") not in SEVERITY:
        return None
    return {"kind": raw["kind"], "severity": raw["severity"], "src": str(raw.get("src", ""))[:64],
            "dst": str(raw.get("dst", ""))[:64], "count": int(raw.get("count") or 0),
            "detail": model.comment(str(raw.get("detail", "")))[:200], "at": time.time()}


class Monitor:

    def __init__(self) -> None:
        self.alerts: deque[dict] = deque(maxlen=500)
        self.summary: dict = {}
        self.connected = False
        self.listeners: list = []
        self.cleaner: asyncio.Task | None = None

    def block_candidate(self, alert: dict) -> model.Address | None:
        policy = store.policy
        if not policy.auto_block or policy.mode not in ("protect", "lockdown"):
            return None
        if SEVERITY[alert["severity"]] < SEVERITY[policy.auto_block_severity]:
            return None
        try:
            address = model.address(alert["src"])
        except ValueError:
            return None
        if address.family == "set" or address.value in _protected() or store.trusted(address):
            return None
        return address

    async def handle(self, line: str) -> None:
        try:
            event = json.loads(line)
        except ValueError:
            return
        if not isinstance(event, dict):
            return
        if event.get("type") == "summary":
            self.summary = {k: event.get(k) for k in ("packets", "bytes", "undecoded", "flows", "dropped_flows",
                                                      "top_flows", "top_talkers")}
            self.summary["at"] = time.time()
            return
        alert = clean_alert(event) if event.get("type") == "alert" else None
        if alert is None:
            return
        self.alerts.append(alert)
        level = "ERROR" if SEVERITY[alert["severity"]] >= SEVERITY["high"] else "WARN"
        system_store.event(level, f"Firewall · {alert['kind']} da {alert['src']}: {alert['detail']}", "firewall")
        self._publish(alert)
        address = self.block_candidate(alert)
        if address is not None:
            from features.firewall.applier import FirewallError
            try:
                await self.block(address, store.policy.auto_block_minutes, f"auto: {alert['kind']}")
            except FirewallError as exc:
                log.error("Blocco automatico di %s non applicato: %s", address.value, exc)
        for listener in list(self.listeners):
            await listener(alert)

    async def block(self, address: model.Address, minutes: int, reason: str) -> dict:
        from features.firewall.applier import applier
        with store.lock:
            store.checkpoint(f"blocco {address.value}")
            store.blocks[address.value] = Block(address, time.time() + minutes * 60, model.comment(reason))
            store.save()
        return await applier.apply(f"blocco di {address.value} per {minutes} min ({reason})")

    def _publish(self, alert: dict) -> None:
        try:
            from atena_bus import BusError, atena_bus
        except ImportError:
            return
        try:
            atena_bus.publish("firewall.alert", alert, origin="firewall")
        except BusError as exc:
            log.warning("Allarme firewall non pubblicato sul bus: %s", exc)

    async def _read(self) -> None:
        reader, writer = await asyncio.open_unix_connection(str(SOCKET), limit=MAX_LINE)
        self.connected = True
        system_store.event("INFO", "Firewall: collegato al motore di analisi del traffico", "firewall")
        try:
            while line := await reader.readline():
                await self.handle(line.decode("utf-8", "replace"))
        finally:
            self.connected = False
            writer.close()

    async def housekeeping(self) -> None:
        from features.firewall.applier import FirewallError, applier
        while True:
            await asyncio.sleep(60)
            if not store.prune():
                continue
            store.save()
            try:
                await applier.apply("scadenza di blocchi o regole")
            except FirewallError as exc:
                log.error("Firewall non aggiornato dopo le scadenze: %s", exc)

    async def run(self) -> None:
        from features.firewall.applier import FirewallError, applier
        try:
            await applier.apply("avvio di Atena")
        except FirewallError as exc:
            log.error("Firewall non applicato all'avvio: %s", exc)
        if not sys.platform.startswith("linux"):
            return
        self.cleaner = asyncio.get_running_loop().create_task(self.housekeeping())
        delay = 5.0
        while True:
            if SOCKET.exists():
                try:
                    await self._read()
                    delay = 5.0
                except (OSError, asyncio.IncompleteReadError, ValueError) as exc:
                    log.info("Motore di analisi del traffico non raggiungibile: %s", exc)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60.0)


monitor = Monitor()
