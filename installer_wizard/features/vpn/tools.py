from features.agent.registry import tool
from features.vpn.service import service
from features.vpn.store import store


def _find(name: str):
    wanted = str(name or "").strip().lower()
    with store.lock:
        for p in store.profiles.values():
            if p.name.lower() == wanted or p.id == wanted:
                return p
        matches = [p for p in store.profiles.values() if wanted and wanted in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"nessun profilo VPN chiamato «{name}»")


@tool("vpn_status", "elenca le VPN configurate con stato di collegamento", {}, agent="vpn")
async def vpn_status() -> str:
    with store.lock:
        rows = [(p, store.wanted.get(p.id, False)) for p in store.profiles.values()]
    if not rows:
        return "nessuna VPN configurata"
    out = []
    for p, wanted in rows:
        state = service.state.get(p.id, {})
        label = "collegata" if state.get("connected") else ("in collegamento" if wanted else "scollegata")
        out.append(f"- {p.name} ({p.kind}{', server' if p.role == 'server' else ''}): {label}")
    return "\n".join(out)


@tool("vpn_connect", "collega una VPN configurata", {"name": "nome del profilo VPN"}, confirm=True, agent="vpn")
async def vpn_connect(name: str) -> str:
    p = _find(name)
    state = await service.connect(p.id)
    return f"VPN {p.name} collegata" if state.get("connected") else f"VPN {p.name} non collegata: {state.get('error', 'errore')}"


@tool("vpn_disconnect", "scollega una VPN", {"name": "nome del profilo VPN"}, confirm=True, agent="vpn")
async def vpn_disconnect(name: str) -> str:
    p = _find(name)
    await service.disconnect(p.id)
    return f"VPN {p.name} scollegata"
