import asyncio
import os
import shutil
import sys
import time

from state import store as system_store

from features.firewall.nft import compile_script
from features.firewall.store import FIREWALL_DIR, store

NFT_TIMEOUT = 20.0
SCRIPT_FILE = FIREWALL_DIR / "atena_guard.nft"


class FirewallError(RuntimeError):
    pass


def available() -> bool:
    return sys.platform.startswith("linux") and shutil.which("nft") is not None


def render() -> str:
    with store.lock:
        return compile_script(store.policy, list(store.rules.values()), dict(store.sets), list(store.blocks.values()))


async def _nft(*args: str) -> None:
    process = await asyncio.create_subprocess_exec("nft", *args, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(process.communicate(), NFT_TIMEOUT)
    except asyncio.TimeoutError:
        process.kill()
        raise FirewallError("nftables non risponde") from None
    if process.returncode != 0:
        raise FirewallError(err.decode("utf-8", "replace").strip()[:600] or "nftables ha rifiutato le regole")


class Applier:

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.pending: asyncio.Task | None = None
        self.deadline = 0.0
        self.last: dict = {"at": 0.0, "ok": None, "error": "", "mode": store.policy.mode}

    async def _write_and_load(self, script: str) -> None:
        FIREWALL_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SCRIPT_FILE.with_suffix(".tmp")
        tmp.write_text(script, encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(SCRIPT_FILE)
        await _nft("-c", "-f", str(SCRIPT_FILE))
        await _nft("-f", str(SCRIPT_FILE))

    async def apply(self, reason: str, confirm_seconds: int = 0) -> dict:
        async with self.lock:
            script = render()
            if not available():
                self.last = {"at": time.time(), "ok": False, "error": "nftables non disponibile su questo sistema",
                             "mode": store.policy.mode}
                return {**self.last, "script": script}
            try:
                await self._write_and_load(script)
            except (FirewallError, OSError) as exc:
                self.last = {"at": time.time(), "ok": False, "error": str(exc), "mode": store.policy.mode}
                system_store.event("ERROR", f"Firewall non applicato ({reason}): {exc}", "firewall")
                raise FirewallError(str(exc)) from exc
            self.last = {"at": time.time(), "ok": True, "error": "", "mode": store.policy.mode}
            system_store.event("INFO", f"Firewall applicato: {reason}", "firewall")
            self._arm(confirm_seconds)
            return {**self.last, "confirm_by": self.deadline if confirm_seconds else 0.0}

    def _arm(self, seconds: int) -> None:
        self.confirm()
        if seconds <= 0:
            return
        self.deadline = time.time() + seconds
        self.pending = asyncio.get_running_loop().create_task(self._revert_after(seconds))

    async def _revert_after(self, seconds: int) -> None:
        await asyncio.sleep(seconds)
        self.pending = None
        self.deadline = 0.0
        entry = store.rollback()
        if entry is None:
            return
        system_store.event("WARN", f"Firewall: modifica non confermata, ripristinata la configurazione precedente ({entry['reason']})",
                           "firewall")
        await self.apply("ripristino automatico")

    def confirm(self) -> bool:
        task, self.pending = self.pending, None
        self.deadline = 0.0
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def status(self) -> dict:
        return {**self.last, "available": available(), "confirm_by": self.deadline}


applier = Applier()
