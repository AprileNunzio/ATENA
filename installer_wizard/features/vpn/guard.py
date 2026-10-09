import ipaddress
from dataclasses import dataclass

from features.vpn import model

TABLE = "atena_vpn"
LAN4 = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")
LAN6 = ("fc00::/7", "fe80::/10")
MESH_IFACES = {"tailscale": ["tailscale0"], "zerotier": ["zt*"]}


@dataclass(frozen=True)
class Tunnel:
    profile: model.Profile
    endpoints: tuple[tuple[str, int, str], ...] = ()


def interfaces(profile: model.Profile) -> list[str]:
    return MESH_IFACES.get(profile.kind, [profile.interface])


def _set(values: list[str]) -> str:
    return "{ " + ", ".join(values) + " }"


def _iface_set(names: list[str]) -> str:
    return _set([f'"{n}"' for n in names])


def compile_script(tunnels: list[Tunnel]) -> str:
    head = [f"table inet {TABLE}", f"delete table inet {TABLE}"]
    clients = [t for t in tunnels if t.profile.role == "client"]
    servers = [t.profile for t in tunnels if t.profile.role == "server"]
    guarded = [t for t in clients if t.profile.kill_switch]
    dns_guarded = [t for t in clients if t.profile.block_dns_leaks and t.profile.split.mode != "include"]
    full = [t for t in guarded if t.profile.split.mode != "include"]
    partial = [n for t in guarded if t.profile.split.mode == "include" for n in t.profile.split.networks]
    if not guarded and not dns_guarded and not servers:
        return "\n".join(head) + "\n"
    names = sorted({n for t in clients for n in interfaces(t.profile)})
    body = [f"table inet {TABLE} {{"]
    if guarded or dns_guarded:
        body += ["    chain output {", "        type filter hook output priority filter - 4; policy accept;",
                 '        oifname "lo" accept']
        if names:
            body.append(f"        oifname {_iface_set(names)} accept")
        if any(t.profile.kind == "ipsec" for t in clients):
            body.append("        rt ipsec exists accept")
        for t in clients:
            for ip, port, proto in t.endpoints:
                family = "ip6" if ipaddress.ip_address(ip).version == 6 else "ip"
                body.append(f"        {family} daddr {ip} {proto} dport {port} accept")
        if dns_guarded:
            body.append("        udp dport { 53, 853 } counter drop")
            body.append("        tcp dport { 53, 853 } counter drop")
        for version, family in ((4, "ip"), (6, "ip6")):
            nets = [n for n in partial if ipaddress.ip_network(n).version == version]
            if nets:
                body.append(f"        {family} daddr {_set(nets)} counter reject")
        if full:
            body.append(f"        ip daddr {_set(list(LAN4))} accept")
            body.append(f"        ip6 daddr {_set(list(LAN6))} accept")
            body.append("        counter reject")
        body.append("    }")
    if servers:
        body += ["    chain forward {", "        type filter hook forward priority filter - 4; policy accept;"]
        for p in servers:
            body.append(f'        iifname "{p.interface}" accept')
            body.append(f'        oifname "{p.interface}" ct state established,related accept')
        body.append("    }")
        body += ["    chain postrouting {", "        type nat hook postrouting priority srcnat; policy accept;"]
        for p in servers:
            subnet = ipaddress.ip_network(p.settings["subnet"])
            body.append(f'        ip saddr {subnet} oifname != "{p.interface}" masquerade')
        body.append("    }")
    body.append("}")
    return "\n".join(head + body) + "\n"
