import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

from config import ETC_DIR

from features.vpn import ipsec, mesh, model, openvpn, wireguard

CONF_DIR = ETC_DIR / "vpn"
SWANCTL_DIR = Path("/etc/swanctl/conf.d")
TIMEOUT = 45.0
TOOLS = {"wireguard": "wg-quick", "openvpn": "openvpn", "ipsec": "swanctl", "tailscale": "tailscale", "zerotier": "zerotier-cli"}
HANDSHAKE_FRESH = 180


class VpnError(RuntimeError):
    pass


def available() -> dict[str, bool]:
    linux = sys.platform.startswith("linux")
    return {kind: linux and shutil.which(tool) is not None for kind, tool in TOOLS.items()}


async def run(*args: str, timeout: float = TIMEOUT) -> str:
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError:
        process.kill()
        raise VpnError(f"{args[0]} non risponde") from None
    if process.returncode != 0:
        raise VpnError((err or out).decode("utf-8", "replace").strip()[:500] or f"{args[0]} non riuscito")
    return out.decode("utf-8", "replace")


def write_private(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)
    return str(path)


def files(p: model.Profile) -> list[Path]:
    base = CONF_DIR / p.interface
    return [base.with_suffix(".conf"), base.with_suffix(".ovpn"), base.with_suffix(".auth"), base.with_suffix(".key"),
            SWANCTL_DIR / f"{ipsec.name(p)}.conf"]


def wipe(p: model.Profile) -> None:
    for path in files(p):
        path.unlink(missing_ok=True)


async def _dns(p: model.Profile) -> None:
    if not p.dns or p.kind in ("wireguard", "tailscale") or not shutil.which("resolvectl"):
        return
    await run("resolvectl", "dns", p.interface, *p.dns)
    if p.split.mode != "include":
        await run("resolvectl", "domain", p.interface, "~.")


async def up(p: model.Profile, secrets: dict) -> None:
    if not available().get(p.kind):
        raise VpnError(f"{TOOLS[p.kind]} non è installato")
    if p.kind == "wireguard":
        text = wireguard.render_server(p, secrets) if p.role == "server" else wireguard.render_client(p, secrets)
        path = write_private(CONF_DIR / f"{p.interface}.conf", text)
        if p.role == "server":
            await run("sysctl", "-w", "net.ipv4.ip_forward=1")
        await run("wg-quick", "up", path)
    elif p.kind == "openvpn":
        login = write_private(CONF_DIR / f"{p.interface}.auth", f"{secrets.get('username', '')}\n{secrets.get('password', '')}\n")
        path = write_private(CONF_DIR / f"{p.interface}.ovpn", openvpn.render(p, secrets, login))
        await run("systemd-run", f"--unit=atena-{p.interface}", "--collect", "--property=Restart=on-failure",
                  "--property=RestartSec=5", "openvpn", "--config", path)
        await asyncio.sleep(3)
        await _dns(p)
    elif p.kind == "ipsec":
        write_private(SWANCTL_DIR / f"{ipsec.name(p)}.conf", ipsec.render(p, secrets))
        await run("swanctl", "--load-all")
        await run("swanctl", "--initiate", "--child", ipsec.name(p), "--timeout", "30", timeout=40)
    elif p.kind == "tailscale":
        key_file = write_private(CONF_DIR / f"{p.interface}.key", secrets.get("auth_key", ""))
        await run(*mesh.tailscale_up(p, key_file), timeout=90)
    else:
        for command in mesh.zerotier_join(p):
            await run(*command)


async def down(p: model.Profile) -> None:
    if not available().get(p.kind):
        return
    if p.kind == "wireguard":
        conf = CONF_DIR / f"{p.interface}.conf"
        if conf.exists():
            await run("wg-quick", "down", str(conf))
    elif p.kind == "openvpn":
        await run("systemctl", "stop", f"atena-{p.interface}")
    elif p.kind == "ipsec":
        await run("swanctl", "--terminate", "--ike", ipsec.name(p), "--timeout", "15")
    elif p.kind == "tailscale":
        await run("tailscale", "down")
    else:
        await run(*mesh.zerotier_leave(p))


def _wireguard_state(text: str, now: float) -> dict:
    stamps = [int(line.split()[-1]) for line in text.splitlines() if line.split() and line.split()[-1].isdigit()]
    fresh = [s for s in stamps if s and now - s < HANDSHAKE_FRESH]
    return {"connected": bool(fresh), "peers": len(stamps), "online_peers": len(fresh),
            "last_handshake": max(stamps) if stamps else 0}


async def status(p: model.Profile) -> dict:
    if not available().get(p.kind):
        return {"connected": False, "error": f"{TOOLS[p.kind]} non installato"}
    try:
        if p.kind == "wireguard":
            state = _wireguard_state(await run("wg", "show", p.interface, "latest-handshakes", timeout=10), time.time())
            return state | {"connected": state["connected"] or (p.role == "server")}
        if p.kind == "openvpn":
            await run("systemctl", "is-active", "--quiet", f"atena-{p.interface}", timeout=10)
            await run("ip", "link", "show", p.interface, timeout=10)
            return {"connected": True}
        if p.kind == "ipsec":
            return {"connected": "ESTABLISHED" in await run("swanctl", "--list-sas", "--ike", ipsec.name(p), timeout=10)}
        if p.kind == "tailscale":
            info = json.loads(await run("tailscale", "status", "--json", timeout=10))
            return {"connected": info.get("BackendState") == "Running", "ip": (info.get("TailscaleIPs") or [""])[0]}
        networks = json.loads(await run("zerotier-cli", "-j", "listnetworks", timeout=10))
        found = next((n for n in networks if n.get("nwid") == p.settings["network_id"]), {})
        return {"connected": found.get("status") == "OK", "ip": (found.get("assignedAddresses") or [""])[0]}
    except (VpnError, ValueError, KeyError) as exc:
        return {"connected": False, "error": str(exc)[:200]}
