import time
from datetime import datetime

import psutil

from state import store

IMPORTANT_WINDOW = 6 * 3600
FIREWALL_WINDOW = 24 * 3600
HOT = 85
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
        lines.append(f"Ultimo: {a.get('kind', '?')} da {a.get('src', '?')}"[:120])
    return "brief", {"title": "Firewall", "lines": lines}, 85 if serious else 40


def important() -> tuple[str, dict, int] | None:
    now = time.time()
    seen, lines = set(), []
    for e in reversed(list(store.events)):
        if e.get("level") not in ("WARN", "ERROR") or now - _ts(e) > IMPORTANT_WINDOW:
            continue
        msg = str(e.get("msg", ""))[:120]
        if msg in seen:
            continue
        seen.add(msg)
        lines.append(msg)
        if len(lines) >= 5:
            break
    if not lines:
        return None
    return "brief", {"title": "Da sapere", "lines": lines}, 70


def headlines(items: list[str]) -> tuple[str, dict, int] | None:
    return ("brief", {"title": "Notizie", "lines": items[:5]}, 30) if items else None


COLLECTORS = {"resources": resources, "systems": systems, "firewall": firewall, "important": important}
