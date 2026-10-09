import ipaddress
import re

from features.vpn import model

ALLOWED = {
    "client", "dev", "dev-type", "proto", "remote", "port", "resolv-retry", "nobind", "persist-key", "persist-tun",
    "remote-cert-tls", "cipher", "data-ciphers", "data-ciphers-fallback", "auth", "tls-version-min", "tls-cipher",
    "tls-ciphersuites", "verb", "mute", "key-direction", "pull", "explicit-exit-notify", "reneg-sec", "mssfix",
    "tun-mtu", "fragment", "server-poll-timeout", "connect-retry", "connect-retry-max", "verify-x509-name",
    "auth-nocache", "remote-random", "float", "sndbuf", "rcvbuf", "ping", "ping-restart", "keepalive",
    "auth-user-pass", "comp-lzo", "compress", "allow-compression", "tls-client", "ns-cert-type", "remote-cert-ku",
    "remote-cert-eku", "push-peer-info", "block-outside-dns", "setenv-safe", "ignore-unknown-option", "route-delay",
    "auth-retry", "redirect-gateway", "route-nopull", "dhcp-option",
}
BLOCKS = {"ca", "cert", "key", "tls-auth", "tls-crypt", "tls-crypt-v2", "extra-certs"}
SECRET_BLOCKS = {"key", "tls-auth", "tls-crypt", "tls-crypt-v2"}
IGNORED = {"block-outside-dns", "setenv-safe", "ignore-unknown-option", "redirect-gateway", "route-nopull", "dhcp-option",
           "auth-user-pass", "dev", "dev-type"}
TOKEN = re.compile(r"^[A-Za-z0-9_.:@/+=,\[\]-]{1,128}$")
PEM_LINE = re.compile(r"^[A-Za-z0-9+/=: -]{0,128}$")


def _block_body(lines: list[str], name: str) -> str:
    for line in lines:
        if not PEM_LINE.match(line):
            raise ValueError(f"contenuto non valido nel blocco <{name}>")
    return "\n".join(lines)


def sanitize(text: str) -> tuple[dict, dict]:
    if len(text or "") > 200_000:
        raise ValueError("file .ovpn troppo grande")
    kept: list[str] = []
    blocks: dict[str, str] = {}
    remotes: list[str] = []
    needs_login = False
    open_block, buffer = "", []
    for number, raw in enumerate(str(text).replace("\r", "").split("\n"), 1):
        line = raw.strip()
        if open_block:
            if line == f"</{open_block}>":
                blocks[open_block] = _block_body(buffer, open_block)
                open_block, buffer = "", []
            else:
                buffer.append(line)
            continue
        if not line or line[0] in "#;":
            continue
        tag = re.fullmatch(r"<([a-z0-9-]+)>", line)
        if tag:
            if tag.group(1) not in BLOCKS:
                raise ValueError(f"blocco <{tag.group(1)}> non ammesso")
            open_block = tag.group(1)
            continue
        parts = line.split()
        name, args = parts[0].lower(), parts[1:]
        if name in BLOCKS:
            raise ValueError(f"riga {number}: {name} deve essere incorporato nel file (<{name}>…</{name}>), non un percorso")
        if name not in ALLOWED:
            raise ValueError(f"riga {number}: la direttiva «{name}» non è ammessa per sicurezza")
        if any(not TOKEN.match(a) for a in args):
            raise ValueError(f"riga {number}: valori non validi")
        if name == "dev" and args and not args[0].startswith("tun"):
            raise ValueError("sono supportate solo VPN di tipo tun")
        if name == "auth-user-pass":
            needs_login = True
        if name == "remote":
            if not args:
                raise ValueError(f"riga {number}: remote senza server")
            port = args[1] if len(args) > 1 else "1194"
            remotes.append(model.endpoint_text(model.host(args[0]), int(port)))
        if name not in IGNORED:
            kept.append(" ".join([name, *args]))
    if open_block:
        raise ValueError(f"blocco <{open_block}> non chiuso")
    if not remotes:
        raise ValueError("il file non indica nessun server (remote)")
    if "ca" not in blocks:
        raise ValueError("manca il certificato del server (<ca>)")
    secrets = {"blocks": {k: v for k, v in blocks.items() if k in SECRET_BLOCKS}}
    settings = {"directives": kept, "blocks": {k: v for k, v in blocks.items() if k not in SECRET_BLOCKS},
                "remotes": remotes, "needs_login": needs_login}
    return settings, secrets


def _route(net: str, gateway: str) -> str:
    parsed = ipaddress.ip_network(net)
    if parsed.version == 6:
        return f"route-ipv6 {parsed} {'' if gateway == 'vpn_gateway' else 'net_gateway'}".strip()
    return f"route {parsed.network_address} {parsed.netmask} {gateway}"


def render(profile: model.Profile, secrets: dict, login_file: str) -> str:
    s = profile.settings
    lines = [*s["directives"], f"dev {profile.interface}", "dev-type tun", "script-security 0"]
    if s.get("needs_login"):
        lines.append(f"auth-user-pass {login_file}")
    if profile.split.mode == "include":
        lines.append("route-nopull")
        lines += [_route(n, "vpn_gateway") for n in profile.split.networks]
    elif profile.split.mode == "exclude":
        lines.append("redirect-gateway def1 ipv6")
        lines += [_route(n, "net_gateway") for n in profile.split.networks]
    else:
        lines.append("redirect-gateway def1 ipv6")
    for name, body in {**s["blocks"], **secrets.get("blocks", {})}.items():
        lines += [f"<{name}>", body, f"</{name}>"]
    return "\n".join(lines) + "\n"
