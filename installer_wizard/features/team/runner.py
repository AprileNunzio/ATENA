import asyncio
import json

from features.agent import registry
from features.team import roster
from features.team.board import ACTING, board

SETTLE = 0.4
ATTEMPTS = 2


class NotVerified(RuntimeError):
    pass


def problem(name: str, args: dict, result: str) -> str | None:
    check = registry.TOOLS.get(name, {}).get("verify")
    if check is None:
        return None
    try:
        return check(registry.clean_args(name, args), result)
    except Exception as exc:
        return f"verifica non riuscita: {exc}"


async def execute(name: str, args: dict, agent_id: str) -> str:
    last = ""
    for attempt in range(ATTEMPTS):
        result = await registry.run(name, args)
        await asyncio.sleep(SETTLE if registry.TOOLS[name].get("verify") else 0)
        last = problem(name, args, result) or ""
        if not last:
            return result
        board.post(agent_id, "tutti", f"{name}: esito non confermato ({last}), riprovo" if attempt + 1 < ATTEMPTS else f"{name}: esito non confermato ({last})", "verifica")
    raise NotVerified(f"{name} eseguito ma non confermato: {last}")


async def run_as(name: str, args: dict) -> str:
    agent_id = roster.owner(name)
    shown = json.dumps(registry.clean_args(name, args), ensure_ascii=False)[:120]
    token = ACTING.set(agent_id)
    board.begin(agent_id, f"{name} {shown}")
    try:
        result = await execute(name, args, agent_id)
    except Exception as exc:
        board.end(agent_id)
        board.post(agent_id, "tutti", f"{name} non riuscito: {str(exc)[:120]}", "errore")
        raise
    finally:
        ACTING.reset(token)
    board.end(agent_id, result)
    return result
