import ipaddress
import re
import time
import uuid
from dataclasses import asdict, dataclass, field

ACTIONS = ("accept", "drop", "reject", "limit")
DIRECTIONS = ("input", "output", "forward")
PROTOCOLS = ("any", "tcp", "udp", "icmp")
MODES = ("off", "monitor", "protect", "lockdown")
SEVERITIES = ("low", "medium", "high", "critical")
MAC = re.compile(r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
IFACE = re.compile(r"^[A-Za-z0-9_.:-]{1,15}$")
RATE = re.compile(r"^(\d{1,7})/(second|minute|hour|day)(?:\s+burst\s+(\d{1,6})(?:\s+packets)?)?$")
COMMENT = re.compile(r"[^\w\s.,:()/-]", re.UNICODE)
MAX_ENTRIES = 4096


@dataclass(frozen=True)
class Address:
    family: str
    value: str


def address(raw: str) -> Address:
    text = str(raw or "").strip().lower()
    if text.startswith("@"):
        if not NAME.match(text[1:]):
            raise ValueError(f"nome di gruppo non valido: {raw}")
        return Address("set", text[1:])
    candidate = text.replace("-", ":")
    if MAC.match(candidate):
        return Address("mac", candidate)
    try:
        network = ipaddress.ip_network(text, strict=False)
    except ValueError:
        raise ValueError(f"indirizzo non valido: {raw}") from None
    value = str(network.network_address) if network.num_addresses == 1 else str(network)
    return Address("ip4" if network.version == 4 else "ip6", value)


def port(raw) -> str:
    text = str(raw).strip()
    low, _, high = text.partition("-")
    try:
        first, last = int(low), int(high or low)
    except ValueError:
        raise ValueError(f"porta non valida: {raw}") from None
    if not (1 <= first <= last <= 65535):
        raise ValueError(f"porta non valida: {raw}")
    return str(first) if first == last else f"{first}-{last}"


def rate(raw: str) -> str:
    match = RATE.match(" ".join(str(raw or "").lower().split()))
    if not match or int(match.group(1)) == 0:
        raise ValueError(f"limite non valido: {raw} (es. 20/minute burst 5)")
    count, unit, burst = match.groups()
    return f"{int(count)}/{unit}" + (f" burst {int(burst)} packets" if burst else "")


def comment(raw: str) -> str:
    return COMMENT.sub("", str(raw or ""))[:80].strip()


def _list(value, convert, limit: int = 256) -> list:
    items = value if isinstance(value, list) else [v for v in str(value or "").replace(",", " ").split() if v]
    if len(items) > limit:
        raise ValueError(f"troppi elementi (massimo {limit})")
    return [convert(v) for v in items]


@dataclass
class Rule:
    action: str
    direction: str = "input"
    protocol: str = "any"
    sources: list[Address] = field(default_factory=list)
    destinations: list[Address] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)
    interface: str = ""
    rate: str = ""
    comment: str = ""
    enabled: bool = True
    priority: int = 100
    expires: float = 0.0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def active(self, now: float | None = None) -> bool:
        return self.enabled and (not self.expires or self.expires > (now or time.time()))

    def export(self) -> dict:
        data = asdict(self)
        data["sources"] = [text_of(a) for a in self.sources]
        data["destinations"] = [text_of(a) for a in self.destinations]
        return data


def text_of(a: Address) -> str:
    return f"@{a.value}" if a.family == "set" else a.value


def _choice(value, options: tuple, label: str) -> str:
    text = str(value or options[0]).strip().lower()
    if text not in options:
        raise ValueError(f"{label} non valido: {value}")
    return text


def rule(data: dict) -> Rule:
    if not isinstance(data, dict):
        raise ValueError("regola non valida")
    built = Rule(
        action=_choice(data.get("action"), ACTIONS, "azione"),
        direction=_choice(data.get("direction"), DIRECTIONS, "direzione"),
        protocol=_choice(data.get("protocol"), PROTOCOLS, "protocollo"),
        sources=_list(data.get("sources"), address),
        destinations=_list(data.get("destinations"), address),
        ports=_list(data.get("ports"), port, 64),
        interface=str(data.get("interface") or "").strip(),
        rate=rate(data["rate"]) if data.get("rate") else "",
        comment=comment(data.get("comment", "")),
        enabled=bool(data.get("enabled", True)),
        priority=max(0, min(int(data.get("priority", 100)), 10_000)),
        expires=max(0.0, float(data.get("expires") or 0.0)),
        id=str(data.get("id") or uuid.uuid4().hex[:10])[:16],
    )
    if built.interface and not IFACE.match(built.interface):
        raise ValueError(f"interfaccia non valida: {built.interface}")
    if built.ports and built.protocol not in ("tcp", "udp"):
        raise ValueError("le porte richiedono il protocollo tcp o udp")
    if built.action == "limit" and not built.rate:
        raise ValueError("l'azione limit richiede un limite (es. 20/minute)")
    if any(a.family == "mac" for a in built.destinations):
        raise ValueError("il MAC si può usare solo come origine")
    if built.direction != "input" and any(a.family == "mac" for a in built.sources):
        raise ValueError("il filtro per MAC vale solo per il traffico in ingresso")
    if not re.fullmatch(r"[0-9a-f]{1,16}", built.id):
        raise ValueError("id della regola non valido")
    return built


def address_set(name: str, entries) -> list[Address]:
    if not NAME.match(str(name or "")):
        raise ValueError(f"nome di gruppo non valido: {name}")
    parsed = _list(entries, address, MAX_ENTRIES)
    if any(a.family == "set" for a in parsed):
        raise ValueError("un gruppo non può contenere altri gruppi")
    return parsed


@dataclass
class Policy:
    mode: str = "monitor"
    allow_lan: bool = True
    allow_ping: bool = True
    admin_ports: list[str] = field(default_factory=lambda: ["22", "80", "443", "8080"])
    trusted: list[Address] = field(default_factory=list)
    auto_block: bool = True
    auto_block_severity: str = "high"
    auto_block_minutes: int = 60
    ai_analysis: bool = True
    ai_auto_apply: bool = False
    ai_min_confidence: float = 0.85

    def export(self) -> dict:
        data = asdict(self)
        data["trusted"] = [text_of(a) for a in self.trusted]
        return data


def policy(data: dict, base: Policy | None = None) -> Policy:
    current = base or Policy()
    if not isinstance(data, dict):
        raise ValueError("politica non valida")
    merged = {**current.export(), **data}
    trusted = _list(merged.get("trusted"), address)
    if any(a.family == "set" for a in trusted):
        raise ValueError("gli indirizzi fidati non possono essere gruppi")
    return Policy(
        mode=_choice(merged.get("mode"), MODES, "modalità"),
        allow_lan=bool(merged.get("allow_lan")),
        allow_ping=bool(merged.get("allow_ping")),
        admin_ports=_list(merged.get("admin_ports"), port, 32),
        trusted=trusted,
        auto_block=bool(merged.get("auto_block")),
        auto_block_severity=_choice(merged.get("auto_block_severity"), SEVERITIES, "gravità"),
        auto_block_minutes=max(1, min(int(merged.get("auto_block_minutes", 60)), 43_200)),
        ai_analysis=bool(merged.get("ai_analysis")),
        ai_auto_apply=bool(merged.get("ai_auto_apply")),
        ai_min_confidence=min(max(float(merged.get("ai_min_confidence") or 0.85), 0.5), 0.99),
    )
