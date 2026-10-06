from feature_registry import registry as features

from features.agent import registry
from features.team import roster, runner
from features.team.board import ACTING, board


def _delegation_risk(args: dict) -> bool:
    name = str(args.get("tool", ""))
    return name not in registry.TOOLS or registry.needs_confirm(name, args.get("args") or {})


@registry.tool("team_roster", "elenca tutti gli agenti di Atena con priorità, strumenti e cosa sta facendo ciascuno ora", {}, agent="agent")
async def team_roster() -> str:
    return roster.team_text() + "\n" + board.digest()


@registry.tool("agent_info", "scheda completa di un agente: cosa sa fare, impostazioni attuali, strumenti, cosa sta facendo e messaggi ricevuti",
               {"agent": "id o nome dell'agente"}, agent="agent")
async def agent_info(agent: str) -> str:
    p = roster.profile(roster.find(agent))
    lines = [f"{p['name']} ({p['id']}) — priorità {p['priority']} — {'attivo' if p['enabled'] else 'SPENTO: ' + p['reason']}", p["description"]]
    lines += [f"• {c}" for c in p["can"]]
    lines += [f"impostazione {s['key']} ({s['label']}) = {s['value'] or '—'}" + (f" [scelte: {', '.join(map(str, s['options']))}]" if s["options"] else "")
              for s in p["settings"]]
    lines += [f"strumento {t['name']}({', '.join(t['args'])}): {t['description']}" for t in p["tools"]]
    lines.append(f"ora: {p['doing'] or 'a riposo'}; messaggi in attesa: {p['inbox']}")
    return "\n".join(lines)


@registry.tool("agent_tell", "lascia un messaggio a un altro agente (lo vedrà come promemoria) e lo annuncia alla squadra",
               {"to": "id dell'agente destinatario", "text": "messaggio"}, agent="agent")
async def agent_tell(to: str, text: str) -> str:
    target = roster.find(to)
    board.post(ACTING.get(), target, text)
    return f"messaggio consegnato a {target}"


@registry.tool("agent_inbox", "legge e svuota i messaggi ricevuti da un agente", {"agent": "id dell'agente"}, agent="agent")
async def agent_inbox(agent: str) -> str:
    rows = board.read(roster.find(agent))
    return "\n".join(f"- da {m['from']}: {m['text']}" for m in rows) or "nessun messaggio"


@registry.tool("agent_ask", "chiede a un agente di eseguire uno dei SUOI strumenti (delega tra agenti, con le stesse conferme dell'originale)",
               {"agent": "id dell'agente", "tool": "nome dello strumento di quell'agente", "args": "argomenti JSON"}, confirm=_delegation_risk, agent="agent")
async def agent_ask(agent: str, tool: str, args: dict | None = None) -> str:
    target = roster.find(agent)
    if tool not in registry.TOOLS or roster.owner(tool) != target:
        raise ValueError(f"{target} non ha lo strumento «{tool}»")
    if tool.startswith("agent_") or tool.startswith("team_"):
        raise ValueError("la delega non può chiamare gli strumenti di coordinamento")
    board.post(ACTING.get(), target, f"ti chiedo di eseguire {tool}", "richiesta")
    return await runner.run_as(tool, args if isinstance(args, dict) else {})


@registry.tool("agent_set", "cambia un'impostazione di un agente (solo tra quelle che l'agente dichiara)",
               {"agent": "id dell'agente", "key": "chiave dell'impostazione", "value": "nuovo valore"}, confirm=True, agent="agent")
async def agent_set(agent: str, key: str, value: str) -> str:
    from settings import apply_config
    target = roster.find(agent)
    if key not in {s["key"] for s in features.features[target].get("settings", [])}:
        raise ValueError(f"{target} non ha l'impostazione «{key}»")
    env_updates, steps = features.save_settings(target, {key: value})
    if env_updates:
        await apply_config(env_updates, "agente", steps)
    board.post(ACTING.get(), target, f"impostazione {key} cambiata", "impostazioni")
    return f"{key} di {target} impostata a «{str(value)[:80]}»"
