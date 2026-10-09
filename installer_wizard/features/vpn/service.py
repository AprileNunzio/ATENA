import asyncio
import ipaddress
import logging
import socket
import sys
import time

from state import store as system_store

from features.vpn import guard, model, runner
from features.vpn.store import VPN_DIR, store

CHECK_EVERY = 20.0
MAX_BACKOFF = 300.0
GUARD_FILE = VPN_DIR / "atena_vpn.nft"
log = logging.getLogger("atena.vpn")


def _endpoints(p: model.Profile) -> tuple[tuple[str, int, str], ...]:
    raw: list[tuple[str, int, str]] = []
    if p.kind == "wireguard" and p.role == "client":
        name, port = model.endpoint(p.settings["endpoint"])
        raw.append((name, port, "udp"))
    elif p.kind == "openvpn":
        for remote in p.settings.get("remotes") or []:
            name, port = model.endpoint(remote)
            raw += [(name, port, "udp"), (name, port, "tcp")]
    elif p.kind == "ipsec":
        raw += [(p.settings["server"], 500, "udp"), (p.settings["server"], 4500, "udp")]
    resolved = []
    for name, port, proto in raw:
        try:
            addresses = {name} if _is_ip(name) else {info[4][0] for info in socket.getaddrinfo(name, port)}
        except OSError:
            addresses = set()
        resolved += [(a, port, proto) for a in sorted(addresses)]
    return tuple(resolved)


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


class VpnService:

    def __init__(self) -> None:
        self.state: dict[str, dict] = {}
        self.failures: dict[str, int] = {}
        self.retry_at: dict[str, float] = {}
        self.endpoints: dict[str, tuple] = {}
        self.lock = asyncio.Lock()
        self.guard_error = ""

    def tunnels(self) -> list[guard.Tunnel]:
        with store.lock:
            active = [p for p in store.profiles.values() if store.wanted.get(p.id)]
        return [guard.Tunnel(p, self.endpoints.get(p.id, ())) for p in active]

    async def apply_guard(self) -> None:
        from features.firewall.applier import FirewallError, available, run_nft
        script = guard.compile_script(self.tunnels())
        if not available():
            return
        VPN_DIR.mkdir(parents=True, exist_ok=True)
        GUARD_FILE.write_text(script, encoding="utf-8")
        try:
            await run_nft("-c", "-f", str(GUARD_FILE))
            await run_nft("-f", str(GUARD_FILE))
            self.guard_error = ""
        except FirewallError as exc:
            self.guard_error = str(exc)
            system_store.event("ERROR", f"VPN: protezioni di rete non applicate: {exc}", "vpn")

    async def connect(self, pid: str) -> dict:
        async with self.lock:
            p = store.get(pid)
            with store.lock:
                store.wanted[pid] = True
                store.save()
            self.endpoints[pid] = await asyncio.to_thread(_endpoints, p)
            await self.apply_guard()
            try:
                await runner.up(p, store.secrets(pid))
            except runner.VpnError as exc:
                self._failed(pid, str(exc))
                return {"connected": False, "error": str(exc)}
            self.failures.pop(pid, None)
            self.state[pid] = await runner.status(p)
            system_store.event("INFO", f"VPN «{p.name}» collegata", "vpn")
            return self.state[pid]

    async def disconnect(self, pid: str) -> dict:
        async with self.lock:
            p = store.get(pid)
            with store.lock:
                store.wanted[pid] = False
                store.save()
            try:
                await runner.down(p)
            except runner.VpnError as exc:
                system_store.event("WARN", f"VPN «{p.name}»: arresto non pulito: {exc}", "vpn")
            runner.wipe(p)
            self.state[pid] = {"connected": False}
            await self.apply_guard()
            system_store.event("INFO", f"VPN «{p.name}» scollegata", "vpn")
            return self.state[pid]

    def _failed(self, pid: str, error: str) -> None:
        count = self.failures.get(pid, 0) + 1
        self.failures[pid] = count
        self.retry_at[pid] = time.time() + min(MAX_BACKOFF, 10 * 2 ** min(count, 5))
        self.state[pid] = {"connected": False, "error": error[:200]}
        system_store.event("WARN", f"VPN: collegamento non riuscito ({count}° tentativo): {error[:160]}", "vpn")

    async def check(self) -> None:
        with store.lock:
            wanted = [store.profiles[pid] for pid, on in store.wanted.items() if on and pid in store.profiles]
        for p in wanted:
            current = await runner.status(p)
            waiting = not current.get("connected") and time.time() < self.retry_at.get(p.id, 0)
            if waiting:
                current = current | {"error": self.state.get(p.id, {}).get("error", ""), "retry_at": self.retry_at[p.id]}
            self.state[p.id] = current
            if current.get("connected") or waiting:
                continue
            system_store.event("WARN", f"VPN «{p.name}» caduta: riconnessione in corso", "vpn")
            try:
                await runner.down(p)
            except runner.VpnError as exc:
                log.info("Arresto prima della riconnessione: %s", exc)
            async with self.lock:
                try:
                    await runner.up(p, store.secrets(p.id))
                    self.failures.pop(p.id, None)
                except runner.VpnError as exc:
                    self._failed(p.id, str(exc))

    async def run(self) -> None:
        if not sys.platform.startswith("linux"):
            return
        with store.lock:
            ids = [pid for pid, on in store.wanted.items() if on]
        for pid in ids:
            await self.connect(pid)
        await self.apply_guard()
        while True:
            await asyncio.sleep(CHECK_EVERY)
            await self.check()


service = VpnService()
