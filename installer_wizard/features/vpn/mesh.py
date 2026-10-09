import re

from features.vpn import model

ZEROTIER_NETWORK = re.compile(r"^[0-9a-f]{16}$")
AUTH_KEY = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
URL = re.compile(r"^https://[A-Za-z0-9.-]{1,253}(?::\d{1,5})?/?$")


def tailscale_settings(data: dict) -> dict:
    server = str(data.get("login_server") or "").strip()
    if server and not URL.match(server):
        raise ValueError("server di accesso non valido (es. https://headscale.example.com)")
    exit_node = str(data.get("exit_node") or "").strip()
    return {
        "login_server": server.rstrip("/"),
        "accept_routes": bool(data.get("accept_routes", True)),
        "exit_node": model.address(exit_node) if exit_node else "",
        "advertise_routes": [model.network(n) for n in data.get("advertise_routes") or []],
        "advertise_exit_node": bool(data.get("advertise_exit_node")),
    }


def auth_key(raw: str) -> str:
    text = str(raw or "").strip()
    if not AUTH_KEY.match(text):
        raise ValueError("chiave di autorizzazione non valida")
    return text


def tailscale_up(profile: model.Profile, key_file: str) -> list[str]:
    s = profile.settings
    args = ["tailscale", "up", f"--auth-key=file:{key_file}", "--reset", f"--accept-routes={str(s['accept_routes']).lower()}",
            f"--accept-dns={str(not profile.dns).lower()}", f"--advertise-exit-node={str(s['advertise_exit_node']).lower()}"]
    if s["login_server"]:
        args.append(f"--login-server={s['login_server']}")
    if s["exit_node"]:
        args += [f"--exit-node={s['exit_node']}", "--exit-node-allow-lan-access=true"]
    if s["advertise_routes"]:
        args.append(f"--advertise-routes={','.join(s['advertise_routes'])}")
    return args


def zerotier_settings(data: dict) -> dict:
    network = str(data.get("network_id") or "").strip().lower()
    if not ZEROTIER_NETWORK.match(network):
        raise ValueError("ID della rete ZeroTier non valido (16 caratteri esadecimali)")
    return {"network_id": network, "allow_default": bool(data.get("allow_default"))}


def zerotier_join(profile: model.Profile) -> list[list[str]]:
    network = profile.settings["network_id"]
    return [["zerotier-cli", "join", network],
            ["zerotier-cli", "set", network, f"allowDefault={1 if profile.settings['allow_default'] else 0}"]]


def zerotier_leave(profile: model.Profile) -> list[str]:
    return ["zerotier-cli", "leave", profile.settings["network_id"]]
