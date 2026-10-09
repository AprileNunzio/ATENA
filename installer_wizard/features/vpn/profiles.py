from features.vpn import ipsec, mesh, model, openvpn, wireguard

SECRET_FIELD = 512
EDITABLE = ("name", "autostart", "kill_switch", "block_dns_leaks", "dns", "split")
EVERYTHING = {"0.0.0.0/0", "::/0"}


def text_value(value, limit: int = SECRET_FIELD) -> str:
    text = str(value or "")
    if len(text) > limit or "\n" in text or "\r" in text:
        raise ValueError("valore non valido")
    return text


def _wireguard_client(body: dict, given: dict) -> tuple[dict, dict, dict]:
    imported = str(body.get("import") or "")
    if imported:
        settings, secrets = wireguard.parse(imported)
        extra = {"dns": settings.pop("dns")}
        allowed = settings.pop("allowed")
        if allowed and set(allowed) - EVERYTHING and not body.get("split"):
            extra["split"] = {"mode": "include", "networks": allowed}
        return settings, secrets, extra
    settings = wireguard.client_settings(body.get("settings") or {})
    if given.get("private_key"):
        private = wireguard.key(given["private_key"])
    else:
        private, _ = wireguard.keypair()
    secrets = {"private_key": private}
    if given.get("preshared_key"):
        secrets["preshared_key"] = wireguard.key(given["preshared_key"])
    return settings, secrets, {}


def build(body: dict) -> tuple[model.Profile, dict]:
    if not isinstance(body, dict):
        raise ValueError("richiesta non valida")
    kind, role = str(body.get("kind") or "").lower(), str(body.get("role") or "client").lower()
    given = body.get("secrets") if isinstance(body.get("secrets"), dict) else {}
    extra: dict = {}
    if kind == "wireguard" and role == "server":
        settings = wireguard.server_settings(body.get("settings") or {})
        private, _ = wireguard.keypair()
        secrets = {"private_key": private, "peers": {}}
    elif kind == "wireguard":
        settings, secrets, extra = _wireguard_client(body, given)
    elif kind == "openvpn":
        settings, secrets = openvpn.sanitize(str(body.get("import") or ""))
        secrets |= {"username": text_value(given.get("username"), 256), "password": text_value(given.get("password"))}
        if settings["needs_login"] and not secrets["username"]:
            raise ValueError("questo profilo OpenVPN richiede nome utente e password")
    elif kind == "ipsec":
        settings = ipsec.settings(body.get("settings") or {})
        secrets = {"secret": ipsec.secret(given.get("secret"))}
    elif kind == "tailscale":
        settings = mesh.tailscale_settings(body.get("settings") or {})
        secrets = {"auth_key": mesh.auth_key(given.get("auth_key"))}
    elif kind == "zerotier":
        settings, secrets = mesh.zerotier_settings(body.get("settings") or {}), {}
    else:
        raise ValueError(f"tipo di VPN non supportato: {kind}")
    data = {k: body[k] for k in EDITABLE if k in body} | {"kind": kind, "role": role}
    for key, value in extra.items():
        data.setdefault(key, value)
    return model.profile(data, settings), secrets


def update(current: model.Profile, body: dict) -> model.Profile:
    if not isinstance(body, dict):
        raise ValueError("richiesta non valida")
    data = current.export() | {k: body[k] for k in EDITABLE if k in body} | {"id": current.id}
    settings = dict(current.settings)
    if current.kind == "wireguard" and current.role == "server" and isinstance(body.get("settings"), dict):
        settings = wireguard.server_settings(body["settings"], settings)
    return model.profile(data, settings)


def public_key(secrets: dict) -> str:
    return wireguard.public_of(secrets["private_key"]) if secrets.get("private_key") else ""


def describe(p: model.Profile, secrets: dict) -> dict:
    row = p.export()
    row["public_key"] = public_key(secrets) if p.kind == "wireguard" else ""
    row["has_password"] = bool(secrets.get("password") or secrets.get("secret") or secrets.get("auth_key"))
    return row
