import base64
import binascii
import ipaddress
import os
import re
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from features.vpn import model

DANGEROUS = {"preup", "postup", "predown", "postdown", "saveconfig", "table"}
INTERFACE_KEYS = {"privatekey", "address", "dns", "mtu", "listenport"}
PEER_KEYS = {"publickey", "presharedkey", "endpoint", "allowedips", "persistentkeepalive"}
PEER_NAME = re.compile(r"^[\w .'-]{1,32}$", re.UNICODE)


def key(raw: str) -> str:
    text = str(raw or "").strip()
    try:
        decoded = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("chiave WireGuard non valida") from None
    if len(decoded) != 32:
        raise ValueError("chiave WireGuard non valida")
    return text


def keypair() -> tuple[str, str]:
    private = X25519PrivateKey.generate()
    raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    return base64.b64encode(raw).decode(), public_of(base64.b64encode(raw).decode())


def public_of(private_key: str) -> str:
    raw = base64.b64decode(key(private_key))
    public = X25519PrivateKey.from_private_bytes(raw).public_key()
    return base64.b64encode(public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()


def preshared() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def parse(text: str) -> tuple[dict, dict]:
    if len(text or "") > 20_000:
        raise ValueError("file di configurazione troppo grande")
    sections: list[tuple[str, dict]] = []
    for number, line in enumerate(str(text).splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            sections.append((line[1:-1].strip().lower(), {}))
            continue
        name, sep, value = line.partition("=")
        name = name.strip().lower()
        if not sep or not sections:
            raise ValueError(f"riga {number} non valida")
        if name in DANGEROUS:
            raise ValueError(f"la direttiva {name} esegue comandi o cambia il routing di sistema e non è ammessa")
        allowed = INTERFACE_KEYS if sections[-1][0] == "interface" else PEER_KEYS
        if name not in allowed:
            raise ValueError(f"direttiva sconosciuta: {name}")
        sections[-1][1][name] = value.strip()
    interfaces = [s for n, s in sections if n == "interface"]
    peers = [s for n, s in sections if n == "peer"]
    if len(interfaces) != 1 or len(peers) != 1:
        raise ValueError("serve esattamente una sezione [Interface] e una [Peer]")
    iface, peer = interfaces[0], peers[0]
    settings = {
        "address": [model.network(a) for a in iface.get("address", "").split(",") if a.strip()],
        "peer_public_key": key(peer.get("publickey", "")),
        "endpoint": model.endpoint_text(*model.endpoint(peer.get("endpoint", ""))),
        "keepalive": max(0, min(int(peer.get("persistentkeepalive") or 25), 3600)),
        "mtu": max(1280, min(int(iface.get("mtu") or 1420), 9000)),
    }
    if not settings["address"]:
        raise ValueError("manca l'indirizzo del tunnel (Address)")
    secrets = {"private_key": key(iface.get("privatekey", ""))}
    if peer.get("presharedkey"):
        secrets["preshared_key"] = key(peer["presharedkey"])
    extra = {"dns": [model.address(d) for d in iface.get("dns", "").split(",") if d.strip()],
             "allowed": [model.network(n) for n in peer.get("allowedips", "").split(",") if n.strip()]}
    return settings | extra, secrets


def client_settings(data: dict) -> dict:
    return {
        "address": [model.network(a) for a in data.get("address") or []] or _missing("indirizzo del tunnel"),
        "peer_public_key": key(data.get("peer_public_key", "")),
        "endpoint": model.endpoint_text(*model.endpoint(data.get("endpoint", ""))),
        "keepalive": max(0, min(int(data.get("keepalive") or 25), 3600)),
        "mtu": max(1280, min(int(data.get("mtu") or 1420), 9000)),
    }


def _missing(what: str):
    raise ValueError(f"manca {what}")


def render_client(profile: model.Profile, secrets: dict) -> str:
    s = profile.settings
    lines = ["[Interface]", f"PrivateKey = {key(secrets['private_key'])}", f"Address = {', '.join(s['address'])}",
             f"MTU = {s['mtu']}"]
    if profile.dns:
        lines.append(f"DNS = {', '.join(profile.dns)}")
    lines += ["", "[Peer]", f"PublicKey = {s['peer_public_key']}", f"Endpoint = {s['endpoint']}",
              f"AllowedIPs = {', '.join(model.routes(profile.split))}"]
    if secrets.get("preshared_key"):
        lines.append(f"PresharedKey = {key(secrets['preshared_key'])}")
    if s["keepalive"]:
        lines.append(f"PersistentKeepalive = {s['keepalive']}")
    return "\n".join(lines) + "\n"


def server_settings(data: dict, current: dict | None = None) -> dict:
    current = current or {}
    subnet = ipaddress.ip_network(model.network(data.get("subnet") or current.get("subnet") or "10.66.0.0/24"))
    if subnet.version != 4 or not subnet.is_private or subnet.prefixlen > 29:
        raise ValueError("la rete del server VPN deve essere IPv4 privata, da /29 a /8")
    return {
        "subnet": str(subnet),
        "listen_port": max(1024, min(int(data.get("listen_port") or current.get("listen_port") or 51820), 65535)),
        "public_host": model.host(data.get("public_host") or current.get("public_host") or "atena.local"),
        "peers": list(current.get("peers") or []),
        "lan_access": bool(data.get("lan_access", current.get("lan_access", True))),
    }


def add_peer(settings: dict, name: str) -> tuple[dict, dict]:
    if not PEER_NAME.match(str(name or "")):
        raise ValueError("nome del dispositivo non valido")
    subnet = ipaddress.ip_network(settings["subnet"])
    used = {ipaddress.ip_interface(p["address"]).ip for p in settings["peers"]}
    hosts = list(subnet.hosts())
    free = next((h for h in hosts[1:] if h not in used), None)
    if free is None:
        raise ValueError("la rete del server VPN è piena")
    private, public = keypair()
    peer = {"id": uuid.uuid4().hex[:8], "name": name.strip(), "address": f"{free}/32", "public_key": public}
    settings["peers"].append(peer)
    return peer, {"private_key": private, "preshared_key": preshared()}


def render_server(profile: model.Profile, secrets: dict) -> str:
    s = profile.settings
    subnet = ipaddress.ip_network(s["subnet"])
    gateway = next(iter(subnet.hosts()))
    lines = ["[Interface]", f"PrivateKey = {key(secrets['private_key'])}", f"Address = {gateway}/{subnet.prefixlen}",
             f"ListenPort = {s['listen_port']}"]
    for peer in s["peers"]:
        peer_secret = secrets.get("peers", {}).get(peer["id"], {})
        lines += ["", f"# {peer['id']}", "[Peer]", f"PublicKey = {key(peer['public_key'])}", f"AllowedIPs = {peer['address']}"]
        if peer_secret.get("preshared_key"):
            lines.append(f"PresharedKey = {key(peer_secret['preshared_key'])}")
    return "\n".join(lines) + "\n"


def render_peer(profile: model.Profile, server_public: str, peer: dict, peer_secret: dict, lan: list[str]) -> str:
    s = profile.settings
    routed = [s["subnet"]] + (lan if s.get("lan_access") else [])
    lines = ["[Interface]", f"PrivateKey = {key(peer_secret['private_key'])}", f"Address = {peer['address']}"]
    if profile.dns:
        lines.append(f"DNS = {', '.join(profile.dns)}")
    lines += ["", "[Peer]", f"PublicKey = {key(server_public)}", f"PresharedKey = {key(peer_secret['preshared_key'])}",
              f"Endpoint = {model.endpoint_text(s['public_host'], s['listen_port'])}",
              f"AllowedIPs = {', '.join(dict.fromkeys(routed))}", "PersistentKeepalive = 25"]
    return "\n".join(lines) + "\n"
