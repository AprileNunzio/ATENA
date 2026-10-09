import ipaddress
import re
import uuid
from dataclasses import asdict, dataclass, field

KINDS = ("wireguard", "openvpn", "ipsec", "tailscale", "zerotier")
TUNNELS = ("wireguard", "openvpn", "ipsec")
ROLES = ("client", "server")
SPLIT_MODES = ("all", "include", "exclude")
NAME = re.compile(r"^[\w .,'()-]{1,48}$", re.UNICODE)
HOST = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")
IFNAME = re.compile(r"^vpn[0-9a-f]{6}$")


def network(raw: str) -> str:
    try:
        return str(ipaddress.ip_network(str(raw).strip(), strict=False))
    except ValueError:
        raise ValueError(f"rete non valida: {raw}") from None


def address(raw: str) -> str:
    try:
        return str(ipaddress.ip_address(str(raw).strip()))
    except ValueError:
        raise ValueError(f"indirizzo non valido: {raw}") from None


def host(raw: str) -> str:
    text = str(raw or "").strip().lower()
    try:
        return str(ipaddress.ip_address(text.strip("[]")))
    except ValueError:
        if not HOST.match(text):
            raise ValueError(f"host non valido: {raw}") from None
        return text


def endpoint(raw: str) -> tuple[str, int]:
    text = str(raw or "").strip()
    if text.startswith("["):
        name, _, rest = text[1:].partition("]")
        port = rest.lstrip(":")
    else:
        name, _, port = text.rpartition(":")
    try:
        number = int(port)
    except ValueError:
        raise ValueError(f"endpoint non valido: {raw} (host:porta)") from None
    if not 1 <= number <= 65535:
        raise ValueError(f"porta non valida in {raw}")
    return host(name), number


def endpoint_text(name: str, port: int) -> str:
    return f"[{name}]:{port}" if ":" in name else f"{name}:{port}"


def _list(value, convert, limit: int = 128) -> list:
    items = value if isinstance(value, list) else [v for v in str(value or "").replace(",", " ").split() if v]
    if len(items) > limit:
        raise ValueError(f"troppi elementi (massimo {limit})")
    return [convert(v) for v in items]


@dataclass
class Split:
    mode: str = "all"
    networks: list[str] = field(default_factory=list)


def split(data) -> Split:
    data = data if isinstance(data, dict) else {}
    mode = str(data.get("mode") or "all").lower()
    if mode not in SPLIT_MODES:
        raise ValueError(f"modalità di split tunneling non valida: {mode}")
    nets = _list(data.get("networks"), network)
    if mode != "all" and not nets:
        raise ValueError("indica almeno una rete per lo split tunneling")
    return Split(mode, nets)


def routes(s: Split) -> list[str]:
    if s.mode == "include":
        return list(s.networks)
    everything = [ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0")]
    if s.mode == "all":
        return [str(n) for n in everything]
    kept: list = []
    for base in everything:
        pieces = [base]
        for raw in s.networks:
            hole = ipaddress.ip_network(raw)
            if hole.version != base.version:
                continue
            next_pieces = []
            for piece in pieces:
                if hole.subnet_of(piece):
                    next_pieces.extend(piece.address_exclude(hole))
                elif not piece.subnet_of(hole):
                    next_pieces.append(piece)
            pieces = next_pieces
        kept.extend(ipaddress.collapse_addresses(pieces))
    return [str(n) for n in kept]


@dataclass
class Profile:
    name: str
    kind: str
    role: str = "client"
    autostart: bool = False
    kill_switch: bool = False
    block_dns_leaks: bool = True
    dns: list[str] = field(default_factory=list)
    split: Split = field(default_factory=Split)
    settings: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:6])

    @property
    def interface(self) -> str:
        return f"vpn{self.id}"

    def export(self) -> dict:
        return asdict(self) | {"interface": self.interface}


def profile(data: dict, settings: dict) -> Profile:
    if not isinstance(data, dict):
        raise ValueError("profilo non valido")
    name = str(data.get("name") or "").strip()
    if not NAME.match(name):
        raise ValueError("nome del profilo non valido (massimo 48 caratteri)")
    kind = str(data.get("kind") or "").lower()
    role = str(data.get("role") or "client").lower()
    if kind not in KINDS:
        raise ValueError(f"tipo di VPN non supportato: {kind}")
    if role not in ROLES or (role == "server" and kind != "wireguard"):
        raise ValueError("solo WireGuard può fare da server VPN")
    built = Profile(
        name=name, kind=kind, role=role, autostart=bool(data.get("autostart")),
        kill_switch=bool(data.get("kill_switch")) and role == "client" and kind in TUNNELS,
        block_dns_leaks=bool(data.get("block_dns_leaks", True)),
        dns=_list(data.get("dns"), address, 8), split=split(data.get("split")), settings=settings,
        id=str(data.get("id") or uuid.uuid4().hex[:6]),
    )
    if not IFNAME.match(built.interface):
        raise ValueError("identificativo del profilo non valido")
    return built
