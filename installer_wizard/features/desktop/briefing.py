import time
from datetime import datetime

import psutil

from state import store

IMPORTANT_WINDOW = 6 * 3600
FIREWALL_WINDOW = 24 * 3600
HOT = 85
NEW_DEVICE_WINDOW = 24 * 3600
NEWS_PAGE = 3
MODES = {"off": "spento", "monitor": "solo osservazione", "protect": "protezione", "lockdown": "blindato"}


def _ts(entry: dict) -> float:
    try:
        return datetime.fromisoformat(str(entry.get("ts", ""))).timestamp()
    except ValueError:
        return 0.0


def resources() -> tuple[str, dict, int]:
    from features.governor.service import governor
    last = governor.last or {}
    disk = psutil.disk_usage("/").percent
    items = [{"label": "Processore", "value": f"{last.get('cpu', 0):.0f}%", "percent": last.get("cpu", 0)},
             {"label": "Memoria", "value": f"{last.get('mem', 0):.0f}%", "percent": last.get("mem", 0)},
             {"label": "Disco", "value": f"{disk:.0f}%", "percent": disk}]
    if last.get("temp"):
        items.append({"label": "Temperatura", "value": f"{last['temp']:.0f} °C", "percent": min(100, last["temp"])})
    hot = any(i["percent"] >= HOT for i in items)
    return "system_health", {"items": items}, 80 if hot else 45


def systems() -> tuple[str, dict, int]:
    comps = list((store.components or {}).values())
    bad = [c for c in comps if c.get("status") not in ("ok", None)]
    lines = [f"{c.get('label', '?')}: {c.get('detail') or c.get('status')}"[:120] for c in bad[:5]]
    if not bad:
        lines.append(f"Tutti i {len(comps)} servizi funzionano")
    up = store.update or {}
    if up.get("available"):
        lines.append(f"Aggiornamento disponibile: {str(up.get('target_rev') or up.get('remote_rev', ''))[:10]}")
    else:
        lines.append("Atena è aggiornata")
    down = any(c.get("status") == "down" for c in bad)
    return "brief", {"title": "Stato dei sistemi", "lines": lines}, 88 if down else 65 if bad or up.get("available") else 35


def firewall() -> tuple[str, dict, int]:
    from features.firewall.events import monitor
    from features.firewall.store import store as fw
    snap = fw.snapshot()
    now = time.time()
    recent = [a for a in monitor.alerts if now - a["at"] < FIREWALL_WINDOW]
    serious = [a for a in recent if a.get("severity") in ("high", "critical")]
    lines = [f"Modalità: {MODES.get(snap['policy'].get('mode'), '?')}",
             "Analisi del traffico attiva" if monitor.connected else "Analisi del traffico non collegata",
             f"Indirizzi bloccati: {len(snap['blocks'])}",
             f"Allarmi nelle ultime 24 ore: {len(recent)} ({len(serious)} gravi)"]
    if recent:
        a = recent[-1]
        from features.network.whois import describe
        lines.append(f"Ultimo: {a.get('kind', '?')} da {describe(a.get('src', '?'))}"[:120])
    return "brief", {"title": "Firewall", "lines": lines}, 85 if serious else 40


def important() -> tuple[str, dict, int] | None:
    now = time.time()
    seen, lines, details = set(), [], []
    for e in reversed(list(store.events)):
        if e.get("level") not in ("WARN", "ERROR") or now - _ts(e) > IMPORTANT_WINDOW:
            continue
        msg = str(e.get("msg", ""))[:120]
        if msg in seen:
            continue
        seen.add(msg)
        lines.append(msg)
        details.append({"title": "Avviso" if e.get("level") == "WARN" else "Errore", "text": str(e.get("msg", ""))[:1500],
                        "source": str(e.get("component", "")), "at": str(e.get("ts", ""))[:19].replace("T", " ")})
        if len(lines) >= 5:
            break
    if not lines:
        return None
    return "brief", {"title": "Da sapere", "lines": lines, "details": details}, 70


def network() -> tuple[str, dict, int] | None:
    from features.network.explorer import explorer
    devices = list(explorer.devices.values())
    if not devices:
        return None
    now = time.time()
    online = [d for d in devices if d.get("online")]
    fresh = sorted((d for d in devices if now - float(d.get("first_seen") or 0) < NEW_DEVICE_WINDOW),
                   key=lambda d: -float(d.get("first_seen") or 0))[:4]
    lines = [f"Dispositivi connessi: {len(online)} su {len(devices)}"]
    details = [None]
    for d in fresh:
        lines.append(f"Nuovo: {explorer.label(d)} ({d.get('ip') or '?'})"[:120])
        details.append({"title": explorer.label(d), "source": "Rete di casa",
                        "text": f"Indirizzo {d.get('ip') or '?'} · {d.get('vendor') or 'produttore sconosciuto'}"
                                f" · {'fidato' if d.get('trusted') else 'non ancora confermato'}"})
    risky = any(not d.get("trusted") for d in fresh)
    return "brief", {"title": "Rete di casa", "lines": lines, "details": details}, 66 if risky else 32


def sun() -> tuple[str, dict, int] | None:
    from features.desktop.sources import sun_cycle
    data = sun_cycle()
    return ("sun_cycle", data, 20) if data else None


def headlines(items: list[dict], page: int = 0) -> tuple[str, dict, int] | None:
    if not items:
        return None
    pages = max(1, (len(items) + NEWS_PAGE - 1) // NEWS_PAGE)
    start = (page % pages) * NEWS_PAGE
    shown = items[start:start + NEWS_PAGE]
    details = [{"title": n["title"], "text": n["text"], "image": n["image"], "source": "ANSA", "at": n["at"],
                "link": n["link"]} for n in shown]
    title = "Notizie" if pages == 1 else f"Notizie {page % pages + 1}/{pages}"
    return "brief", {"title": title, "lines": [n["title"] for n in shown], "details": details}, 30


COLLECTORS = {"resources": resources, "systems": systems, "firewall": firewall, "important": important,
              "network": network, "sun": sun}
