import re

from features.vpn import model

AUTHS = ("psk", "eap")
IDENT = re.compile(r"^[A-Za-z0-9@._:=,+/-]{1,128}$")
SECRET = re.compile(r"^[\x20-\x7e]{6,256}$")


def _ident(raw: str, label: str, required: bool = False) -> str:
    text = str(raw or "").strip()
    if not text:
        if required:
            raise ValueError(f"manca {label}")
        return ""
    if not IDENT.match(text):
        raise ValueError(f"{label} non valido")
    return text


def settings(data: dict) -> dict:
    auth = str(data.get("auth") or "psk").lower()
    if auth not in AUTHS:
        raise ValueError("autenticazione IPsec non supportata (psk o eap)")
    return {
        "server": model.host(data.get("server") or ""),
        "auth": auth,
        "local_id": _ident(data.get("local_id"), "identità locale"),
        "remote_id": _ident(data.get("remote_id"), "identità del server", required=auth == "eap"),
        "username": _ident(data.get("username"), "nome utente", required=auth == "eap"),
    }


def secret(raw: str) -> str:
    text = str(raw or "")
    if not SECRET.match(text):
        raise ValueError("segreto IPsec non valido (6-256 caratteri stampabili)")
    return text


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def name(profile: model.Profile) -> str:
    return f"atena-{profile.id}"


def render(profile: model.Profile, secrets: dict) -> str:
    s = profile.settings
    conn = name(profile)
    local = [f"auth = {'psk' if s['auth'] == 'psk' else 'eap-mschapv2'}"]
    if s["local_id"]:
        local.append(f"id = {_quote(s['local_id'])}")
    if s["auth"] == "eap":
        local.append(f"eap_id = {_quote(s['username'])}")
    remote = [f"auth = {'psk' if s['auth'] == 'psk' else 'pubkey'}"]
    if s["remote_id"]:
        remote.append(f"id = {_quote(s['remote_id'])}")
    targets = ",".join(model.routes(profile.split))
    lines = ["connections {", f"    {conn} {{", "        version = 2", f"        remote_addrs = {s['server']}",
             "        vips = 0.0.0.0,::", "        proposals = aes256gcm16-prfsha384-ecp384,aes256-sha256-modp2048,default",
             "        dpd_delay = 30s", "        local {", *(f"            {x}" for x in local), "        }",
             "        remote {", *(f"            {x}" for x in remote), "        }", "        children {",
             f"            {conn} {{", f"                remote_ts = {targets}",
             "                esp_proposals = aes256gcm16-ecp384,aes256-sha256,default",
             "                dpd_action = restart", "                close_action = restart", "                start_action = none",
             "            }", "        }", "    }", "}", "secrets {"]
    if s["auth"] == "psk":
        lines += [f"    ike-{conn} {{", f"        secret = {_quote(secret(secrets['secret']))}"]
        if s["remote_id"]:
            lines.append(f"        id-remote = {_quote(s['remote_id'])}")
        lines.append("    }")
    else:
        lines += [f"    eap-{conn} {{", f"        id = {_quote(s['username'])}", f"        secret = {_quote(secret(secrets['secret']))}", "    }"]
    lines.append("}")
    return "\n".join(lines) + "\n"
