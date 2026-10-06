import hashlib
import json

from features.agent import registry
from features.capabilities import manifest
from features.desktop.desk import desk
from features.team import roster

READ_ONLY = ("list_", "find_", "file_info", "read_file", "music_search", "music_now", "music_outputs", "agent_info", "team_roster", "now", "avatar_catalog")
AGENT_URI = "atena://agent/"


def annotations(name: str) -> dict:
    row = registry.TOOLS[name]
    return {"title": name.replace("_", " ").capitalize(), "readOnlyHint": name.startswith(READ_ONLY), "destructiveHint": bool(row["confirm"]),
            "openWorldHint": name in ("http_get", "send_email"), "agent": roster.owner(name), "needsConfirmation": bool(row["confirm"])}


def widgets() -> str:
    desk.scan()
    return json.dumps([{"id": w["id"], "name": w["name"], "description": w.get("description", ""), "size": w["size"], "personal": w["personal"],
                        "source": w["source"]} for w in desk.widgets.values()], ensure_ascii=False)


def resources(visible_agents: set[str] | None) -> list[dict]:
    rows = [{"uri": "atena://capabilities", "name": "Cosa sa fare Atena", "mimeType": "text/plain"},
            {"uri": "atena://team", "name": "Squadra di agenti, priorità e lavagna", "mimeType": "application/json"},
            {"uri": "atena://widgets", "name": "Widget disponibili sul display", "mimeType": "application/json"}]
    rows += [{"uri": AGENT_URI + a, "name": f"Agente {a}", "mimeType": "text/plain"} for a in roster.ids() if visible_agents is None or a in visible_agents]
    return rows


def templates() -> list[dict]:
    return [{"uriTemplate": AGENT_URI + "{id}", "name": "Scheda di un agente", "mimeType": "text/plain"}]


def read(uri: str) -> tuple[str, str]:
    if uri == "atena://capabilities":
        return "text/plain", manifest.summary()
    if uri == "atena://team":
        return "application/json", json.dumps(roster.document(), ensure_ascii=False)
    if uri == "atena://widgets":
        return "application/json", widgets()
    if uri.startswith(AGENT_URI):
        return "text/plain", card(roster.find(uri[len(AGENT_URI):]))
    raise KeyError(uri)


def card(agent_id: str) -> str:
    p = roster.profile(agent_id)
    lines = [f"{p['name']} ({p['id']}) — priorità {p['priority']} — {'attivo' if p['enabled'] else 'spento: ' + p['reason']}", p["description"]]
    lines += [f"• {c}" for c in p["can"]]
    lines += [f"impostazione {s['key']} = {s['value'] or '—'}" for s in p["settings"]]
    lines += [f"strumento {t['name']}: {t['description']}" for t in p["tools"]]
    return "\n".join(lines)


def prompts() -> list[dict]:
    return [{"name": "panoramica", "description": "Cosa sa fare Atena, con le frasi per chiederlo e la squadra di agenti"},
            {"name": "agente", "description": "Scheda completa di un agente di Atena", "arguments": [{"name": "agente", "description": "id o nome", "required": True}]}]


def prompt(name: str, arguments: dict) -> dict:
    if name == "panoramica":
        body = manifest.summary()
    elif name == "agente":
        body = card(roster.find(str(arguments.get("agente", ""))))
    else:
        raise KeyError(name)
    return {"description": name, "messages": [{"role": "user", "content": {"type": "text", "text": body}}]}


def signature(names: list[str]) -> str:
    desk.scan()
    parts = sorted(names) + sorted(desk.widgets) + roster.ids()
    return hashlib.sha1("|".join(parts).encode()).hexdigest()
