import ipaddress
import time

from features.network.explorer import TYPES, explorer

WINDOW = 24 * 3600


def _private(address: str) -> bool | None:
    try:
        ip = ipaddress.ip_address(str(address).split("/")[0])
    except ValueError:
        return None
    return ip.is_private or ip.is_loopback or ip.is_link_local


def device(address: str) -> dict | None:
    address = str(address or "").strip()
    if not address:
        return None
    return next((d for d in explorer.devices.values() if d.get("ip") == address or d.get("mac") == address.lower()), None)


def who(address: str) -> dict | None:
    d = device(address)
    if d is None:
        private = _private(address)
        return None if private is None else {"label": "dispositivo sconosciuto" if private else "Internet", "known": False,
                                              "local": bool(private)}
    return {"label": explorer.label(d), "known": True, "local": True, "key": d.get("key", ""),
            "type": TYPES.get(d.get("type"), TYPES["unknown"])[0], "room": d.get("room", ""), "owner": d.get("owner", ""),
            "trusted": bool(d.get("trusted")), "online": bool(d.get("online"))}


def label(address: str) -> str:
    info = who(address)
    return info["label"] if info else ""


def describe(address: str) -> str:
    name = label(address)
    return f"{address} ({name})" if name else str(address)


def names(addresses) -> dict[str, dict]:
    out = {}
    for a in {str(x) for x in addresses if x}:
        info = who(a)
        if info:
            out[a] = info
    return out


def firewall_view(alerts, blocks: dict) -> dict[str, dict]:
    now = time.time()
    per_key: dict[str, dict] = {}
    for d in explorer.devices.values():
        ip = d.get("ip")
        if not ip:
            continue
        hits = [a for a in alerts if a.get("src") == ip and now - float(a.get("at", 0)) < WINDOW]
        blocked = ip in blocks or (d.get("mac") or "") in blocks
        if hits or blocked:
            per_key[d["key"]] = {"alerts_24h": len(hits), "blocked": blocked,
                                 "last": hits[-1].get("kind", "") if hits else ""}
    return per_key
