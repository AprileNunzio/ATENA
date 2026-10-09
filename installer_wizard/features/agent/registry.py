import inspect
import re
from contextvars import ContextVar

TOOLS: dict[str, dict] = {}
REQUEST: ContextVar[str] = ContextVar("agent_request", default="")
RECURRING = re.compile(r"\b(automazion\w*|ogni|tutti\s+i|tutte\s+le|quando|appena|se\s+\w+|alle\s+\d|alle\s+ore|"
                       r"domani|stasera|stanotte|più\s+tardi|tra\s+\d+|fra\s+\d+|ricordami|programm\w*|pianific\w*|"
                       r"routine|sempre|ogni\s+volta)\b", re.I)


def asked_for_recurring() -> bool:
    request = REQUEST.get()
    return not request or bool(RECURRING.search(request))


def tool(name: str, description: str, args: dict, confirm=False, full_only: bool = False, agent: str = "", verify=None,
         precheck=None):
    def wrap(fn):
        TOOLS[name] = {"name": name, "description": description, "args": args, "fn": fn, "confirm": confirm,
                       "full_only": full_only, "agent": agent, "verify": verify, "precheck": precheck}
        return fn
    return wrap


def available(level: str) -> list[dict]:
    return [t for t in TOOLS.values() if level == "completo" or not t["full_only"]]


def describe(level: str) -> str:
    return describe_for_agents(level, None)

def describe_for_agents(level: str, agents: set[str] | None, permitted=None) -> str:
    from features.team import roster
    rows = []
    for t in available(level):
        if permitted is not None and not permitted(t["name"]):
            continue
        if agents is not None:
            owner = roster.owner(t["name"])
            if owner not in agents:
                continue
        args = ", ".join(f"{k}: {v}" for k, v in t["args"].items())
        rows.append(f"- {t['name']}({args}): {t['description']}")
    return "\n".join(rows)


def clean_args(name: str, args) -> dict:
    fn = TOOLS[name]["fn"]
    params = inspect.signature(fn).parameters
    args = args if isinstance(args, dict) else {}
    return {k: v for k, v in args.items() if k in params}


def needs_confirm(name: str, args: dict) -> bool:
    rule = TOOLS[name]["confirm"]
    if callable(rule):
        try:
            return bool(rule(args))
        except Exception:
            return True
    return bool(rule)


def precheck(name: str, args: dict) -> str:
    check = TOOLS[name].get("precheck")
    if not check:
        return ""
    try:
        check(args if isinstance(args, dict) else {})
    except (ValueError, TypeError, PermissionError, KeyError) as exc:
        return str(exc)[:200] or type(exc).__name__
    return ""


async def run(name: str, args: dict) -> str:
    out = await TOOLS[name]["fn"](**clean_args(name, args))
    return str(out)[:6000]
