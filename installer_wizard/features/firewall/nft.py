import time
from dataclasses import dataclass

from features.firewall.model import Address, Policy, Rule

TABLE = "atena_guard"
LAN4 = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")
LAN6 = ("fc00::/7", "fe80::/10")
FAMILIES = {"ip4": ("ip", "ipv4_addr"), "ip6": ("ip6", "ipv6_addr"), "mac": ("ether", "ether_addr")}


@dataclass(frozen=True)
class Block:
    address: Address
    expires: float
    reason: str = ""


def _elements(values: list[str]) -> str:
    return "{ " + ", ".join(values) + " }"


def _set(name: str, kind: str, values: list[str], timeout: bool = False) -> list[str]:
    flags = "flags interval, timeout" if timeout and kind != "ether_addr" else (
        "flags timeout" if timeout else ("flags interval" if kind != "ether_addr" else ""))
    lines = [f"    set {name} {{", f"        type {kind}"]
    if flags:
        lines.append(f"        {flags}")
    if kind != "ether_addr":
        lines.append("        auto-merge")
    if values:
        lines.append(f"        elements = {_elements(values)}")
    lines.append("    }")
    return lines


def _group(addresses: list[Address]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {"ip4": [], "ip6": [], "mac": [], "set": []}
    for a in addresses:
        grouped[a.family].append(a.value)
    return grouped


def _suffix(family: str) -> str:
    return "mac" if family == "mac" else family[-1]


def _options(side: str, addresses: list[Address], family: str) -> list[str | None]:
    if not addresses:
        return [None]
    grouped = _group(addresses)
    prefix = FAMILIES[family][0]
    options: list[str | None] = []
    if grouped[family]:
        options.append(f"{prefix} {side}addr {_elements(grouped[family])}")
    options.extend(f"{prefix} {side}addr @{name}_{_suffix(family)}" for name in grouped["set"])
    return options


def _verdict(rule: Rule) -> str:
    if rule.action == "limit":
        return f"limit rate over {rule.rate} counter drop"
    return f"counter {rule.action}"


def _rule_lines(rule: Rule) -> list[str]:
    macs = [a.value for a in rule.sources if a.family == "mac"]
    ip_sources = [a for a in rule.sources if a.family != "mac"]
    addressed = ip_sources + rule.destinations
    families = sorted({a.family for a in addressed if a.family in ("ip4", "ip6")}
                      | ({"ip4", "ip6"} if any(a.family == "set" for a in addressed) else set())) or [""]
    head = [f'{"oifname" if rule.direction == "output" else "iifname"} "{rule.interface}"'] if rule.interface else []
    tail = _tail(rule)
    lines = []
    origins: list[tuple[str, list[str | None]]] = []
    if ip_sources or not macs:
        origins += [(family, _options("s", ip_sources, family) if family else [None]) for family in families]
    if macs:
        origins += [(family, [f"ether saddr {_elements(macs)}"]) for family in families]
    if rule.direction == "input" and not rule.destinations:
        origins += [("", [f"ether saddr @{name}_mac"]) for name in _group(ip_sources)["set"]]
    for family, sources in origins:
        targets = _options("d", rule.destinations, family) if family else [None]
        for source in sources:
            for target in targets:
                line = "        " + " ".join(head + [p for p in (source, target) if p] + tail)
                if line not in lines:
                    lines.append(line)
    return lines


def _tail(rule: Rule) -> list[str]:
    parts = []
    if rule.protocol in ("tcp", "udp"):
        parts.append(f"meta l4proto {rule.protocol}")
        if rule.ports:
            parts.append(f"{rule.protocol} dport {_elements(rule.ports)}")
    elif rule.protocol == "icmp":
        parts.append("meta l4proto { icmp, ipv6-icmp }")
    parts.append(_verdict(rule))
    if rule.comment:
        parts.append(f'comment "{rule.comment}"')
    return parts


def _blocks(blocks: list[Block], family: str, now: float) -> list[str]:
    values = []
    for b in blocks:
        left = int(b.expires - now) if b.expires else 0
        if b.address.family != family or (b.expires and left <= 0):
            continue
        values.append(f"{b.address.value} timeout {left}s" if left else b.address.value)
    return values


def _guards(policy: Policy) -> list[str]:
    lines = [
        '        iifname "lo" accept',
        "        ct state established,related accept",
        "        ct state invalid counter drop",
        "        ip saddr @trusted_4 accept",
        "        ip6 saddr @trusted_6 accept",
        "        ether saddr @trusted_mac accept",
        "        ip saddr @blocked_4 counter drop",
        "        ip6 saddr @blocked_6 counter drop",
        "        ether saddr @blocked_mac counter drop",
        "        udp sport 67 udp dport 68 accept",
        "        udp sport 547 udp dport 546 accept",
        "        meta l4proto ipv6-icmp icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert, nd-router-advert } accept",
    ]
    if policy.admin_ports:
        ports = _elements(policy.admin_ports)
        lines.append(f"        ip saddr {_elements(list(LAN4))} tcp dport {ports} accept")
        lines.append(f"        ip6 saddr {_elements(list(LAN6))} tcp dport {ports} accept")
    if policy.allow_ping:
        lines.append("        meta l4proto { icmp, ipv6-icmp } limit rate 20/second accept")
    if policy.allow_lan:
        lines.append(f"        ip saddr {_elements(list(LAN4))} accept")
        lines.append(f"        ip6 saddr {_elements(list(LAN6))} accept")
    return lines


def compile_script(policy: Policy, rules: list[Rule], sets: dict[str, list[Address]], blocks: list[Block],
                   now: float | None = None) -> str:
    now = now or time.time()
    head = [f"table inet {TABLE}", f"delete table inet {TABLE}"]
    if policy.mode in ("off", "monitor"):
        return "\n".join(head) + "\n"
    trusted = _group(policy.trusted)
    body = [f"table inet {TABLE} {{"]
    body += _set("trusted_4", "ipv4_addr", trusted["ip4"]) + _set("trusted_6", "ipv6_addr", trusted["ip6"])
    body += _set("trusted_mac", "ether_addr", trusted["mac"])
    for family, kind in (("ip4", "ipv4_addr"), ("ip6", "ipv6_addr"), ("mac", "ether_addr")):
        body += _set(f"blocked_{_suffix(family)}", kind, _blocks(blocks, family, now), timeout=True)
    for name, entries in sorted(sets.items()):
        grouped = _group(entries)
        body += _set(f"{name}_4", "ipv4_addr", grouped["ip4"]) + _set(f"{name}_6", "ipv6_addr", grouped["ip6"])
        body += _set(f"{name}_mac", "ether_addr", grouped["mac"])
    active = sorted((r for r in rules if r.active(now)), key=lambda r: (r.priority, r.id))
    default = "drop" if policy.mode == "lockdown" else "accept"
    for chain, hook, policy_verdict in (("input", "input", default), ("forward", "forward", "accept"),
                                       ("output", "output", "accept")):
        body.append(f"    chain {chain} {{")
        body.append(f"        type filter hook {hook} priority filter - 5; policy {policy_verdict};")
        if chain == "input":
            body += _guards(policy)
        else:
            body.append("        ct state established,related accept")
            side = "d" if chain == "output" else "s"
            body.append(f"        ip {side}addr @blocked_4 counter drop")
            body.append(f"        ip6 {side}addr @blocked_6 counter drop")
        for rule in active:
            if rule.direction == chain:
                body += _rule_lines(rule)
        body.append("    }")
    body.append("}")
    return "\n".join(head + body) + "\n"
