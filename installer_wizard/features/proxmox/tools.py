from features.agent.registry import tool
from features.proxmox.client import client


def _pct(used, total) -> str:
    return f"{round(100 * float(used or 0) / float(total), 0):.0f}%" if total else "?"


@tool("proxmox_status", "stato dell'hypervisor Proxmox: nodi, macchine virtuali e container con risorse", {}, agent="proxmox")
async def proxmox_status() -> str:
    data = await client.overview()
    rows = [f"nodo {n['node']}: {n['status']}, CPU {_pct(n.get('cpu'), 1)}, RAM {_pct(n.get('mem'), n.get('maxmem'))}"
            for n in data["nodes"]]
    rows += [f"- {g['type']} {g['vmid']} {g.get('name') or ''} su {g['node']}: {g['status']}" for g in data["guests"]]
    return "\n".join(rows) or "nessun nodo"


@tool("proxmox_power", "avvia, spegne, arresta, riavvia, sospende o riprende una VM o un container Proxmox",
      {"vmid": "ID numerico", "action": "start|shutdown|stop|reboot|suspend|resume"}, confirm=True, agent="proxmox")
async def proxmox_power(vmid: int, action: str) -> str:
    data = await client.overview()
    guest = next((g for g in data["guests"] if int(g.get("vmid") or 0) == int(vmid)), None)
    if guest is None:
        raise ValueError(f"nessuna VM o container con ID {vmid}")
    task = await client.power(guest["node"], guest["type"], int(vmid), str(action))
    return f"{action} inviato a {guest['type']} {vmid} ({guest.get('name') or ''}): attività {task}"
