from features.agent.registry import tool
from features.network.whois import describe, device, who


@tool("who_is", "dice chi è un indirizzo IP o MAC della rete di casa (nome del dispositivo, tipo, stanza, proprietario, "
      "se è fidato) e se il firewall lo ha segnalato", {"address": "indirizzo IP o MAC"}, agent="network")
async def who_is(address: str) -> str:
    info = who(address)
    if info is None:
        return f"{address} non è un indirizzo valido"
    if not info["known"]:
        return f"{address}: {info['label']}"
    from features.firewall.events import monitor
    hits = [a for a in monitor.alerts if a.get("src") == device(address).get("ip")]
    parts = [describe(address), info["type"]]
    parts += [f"stanza {info['room']}"] if info["room"] else []
    parts += [f"di {info['owner']}"] if info["owner"] else []
    parts.append("fidato" if info["trusted"] else "non confermato")
    parts.append("connesso" if info["online"] else "non connesso")
    parts.append(f"{len(hits)} allarmi del firewall" if hits else "nessun allarme del firewall")
    return ", ".join(parts)
