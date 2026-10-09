import json

from features.agent.registry import tool
from features.rpa.service import rpa
from features.rpa.steps import parse_steps

STEPS_HELP = ("elenco JSON di passi, ognuno {do: click|double_click|right_click|type|key|scroll|wait, target: descrizione "
              "dell'elemento, text: testo, keys: [tasti], amount: intero, seconds: numero}")


def _precheck(args: dict) -> None:
    node, steps = str(args.get("node") or ""), args.get("steps")
    if not rpa.permitted(node):
        raise PermissionError(f"il controllo dello schermo del nodo «{node}» non è abilitato: per comandi sul server usa run_command")
    parse_steps(json.loads(steps) if isinstance(steps, str) else steps)


@tool("rpa_run", "controlla un computer collegato come farebbe una persona: trova gli elementi sullo schermo, clicca, "
      "scrive e verifica dai pixel che l'azione abbia avuto effetto", {"node": "id del nodo", "steps": STEPS_HELP},
      confirm=True, full_only=True, precheck=_precheck)
async def rpa_run(node: str, steps) -> str:
    if isinstance(steps, str):
        steps = json.loads(steps)
    trace = await rpa.run(str(node), steps)
    detail = "; ".join(f"{s.number}. {s.do}: {s.message or ('ok' if s.ok else 'fallito')}" for s in trace.steps)
    return f"{trace.message}. {detail}"
