from functools import partial

from features.agent.registry import tool
from features.forge import assets, recipes
from features.team.board import board

forge = partial(tool, agent="forge")
recipes.load()


@forge("create_tool", "crea un nuovo strumento riutilizzabile combinando strumenti esistenti in sequenza: ogni passo è {tool, args}; "
       "negli argomenti si usano {{parametro}} e il risultato del passo precedente come {{s1}}, {{s2}}…",
       {"name": "nome in minuscolo con _", "description": "a cosa serve", "params": "oggetto {nome_parametro: descrizione}", "steps": "lista di {tool, args}",
        "agent": "agente a cui appartiene (facoltativo)"})
async def create_tool(name: str, description: str, steps: list, params: dict | None = None, agent: str = "") -> str:
    spec = recipes.save({"name": name, "description": description, "params": params or {}, "steps": steps, "agent": agent or "forge"})
    board.post("forge", "tutti", f"nuovo strumento «{spec['name']}» ({len(spec['steps'])} passi)", "creazione")
    return f"strumento «{spec['name']}» creato: da ora è disponibile ad Atena e a ogni client MCP collegato"


@forge("list_custom_tools", "elenca gli strumenti creati da Atena con i loro passi", {})
async def list_custom_tools() -> str:
    return "\n".join(f"- {s['name']}({', '.join(s['params'])}): {s['description']} → " + " › ".join(st["tool"] for st in s["steps"])
                     for s in recipes.CUSTOM.values()) or "nessuno strumento creato"


@forge("delete_tool", "elimina uno strumento creato da Atena", {"name": "nome dello strumento"}, confirm=True)
async def delete_tool(name: str) -> str:
    if not recipes.remove(name):
        raise ValueError(f"«{name}» non è uno strumento creato da Atena")
    return f"strumento «{name}» eliminato"


@forge("create_widget", "crea un nuovo widget per il display: mostra titolo, valore, testo e/o elenco che passi poi con show_widget (title, value, unit, label, text, items)",
       {"id": "id in minuscolo", "name": "nome", "description": "a cosa serve", "icon": "emoji", "size": "s|m|l", "priority": "0-100", "personal": "true se contiene dati personali"})
async def create_widget(id: str, name: str, description: str = "", icon: str = "", size: str = "m", priority: int = 40, personal=False) -> str:
    manifest = assets.create_widget({"id": id, "name": name, "description": description, "icon": icon, "size": size, "priority": priority,
                                     "personal": str(personal).lower() == "true"})
    board.post("forge", "tutti", f"nuovo widget «{manifest['name']}»", "creazione")
    return f"widget «{manifest['id']}» creato: aprilo con show_widget(id=\"{manifest['id']}\", data={{...}})"


@forge("delete_widget", "elimina un widget creato da Atena", {"id": "id del widget"}, confirm=True)
async def delete_widget(id: str) -> str:
    if not assets.delete_widget(id):
        raise ValueError(f"«{id}» non è un widget creato da Atena")
    return f"widget «{id}» eliminato"


@forge("create_feature", "crea una nuova funzionalità (e quindi un nuovo agente della squadra) con nome, descrizione e capacità",
       {"id": "id in minuscolo", "name": "nome", "description": "cosa fa", "capabilities": "lista di frasi", "category": "assistente|percezione|casa|conoscenza|comunicazione|sistema|altro",
        "icon": "emoji"})
async def create_feature(id: str, name: str, description: str = "", capabilities: list | None = None, category: str = "altro", icon: str = "") -> str:
    manifest = assets.create_feature({"id": id, "name": name, "description": description, "capabilities": capabilities or [], "category": category, "icon": icon})
    board.post("forge", "tutti", f"nuova funzionalità «{manifest['name']}»", "creazione")
    return f"funzionalità «{manifest['id']}» creata: ora è un agente della squadra"


@forge("delete_feature", "elimina una funzionalità creata da Atena", {"id": "id della funzionalità"}, confirm=True)
async def delete_feature(id: str) -> str:
    if not assets.delete_feature(id):
        raise ValueError(f"«{id}» non è una funzionalità creata da Atena")
    return f"funzionalità «{id}» eliminata"
