import inspect
import json
import re

from config import STATE_DIR
from features.agent import registry

DIR = STATE_DIR / "tools"
NAME = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
PARAM = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
SLOT = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
MAX_STEPS = 10
MAX_PARAMS = 8
CUSTOM: dict[str, dict] = {}


def validate(spec: dict) -> dict:
    name = str(spec.get("name", ""))
    if not NAME.match(name):
        raise ValueError("nome non valido: minuscole, cifre e _ (da 3 a 41 caratteri)")
    if name in registry.TOOLS and name not in CUSTOM:
        raise ValueError(f"«{name}» è già uno strumento di sistema")
    steps = spec.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError(f"servono da 1 a {MAX_STEPS} passi")
    params = spec.get("params") or {}
    if not isinstance(params, dict) or len(params) > MAX_PARAMS or not all(PARAM.match(str(k)) for k in params):
        raise ValueError("parametri non validi")
    clean = []
    for index, step in enumerate(steps, 1):
        step = step if isinstance(step, dict) else {}
        tool = str(step.get("tool", ""))
        if tool not in registry.TOOLS or tool in CUSTOM:
            raise ValueError(f"passo {index}: lo strumento «{tool}» non esiste o è personalizzato")
        args = step.get("args") or {}
        if not isinstance(args, dict):
            raise ValueError(f"passo {index}: argomenti non validi")
        known = set(params) | {f"s{n}" for n in range(1, index)}
        unknown = {m for v in args.values() for m in SLOT.findall(json.dumps(v, ensure_ascii=False))} - known
        if unknown:
            raise ValueError(f"passo {index}: segnaposto sconosciuti {sorted(unknown)}")
        clean.append({"tool": tool, "args": args})
    return {"name": name, "description": str(spec.get("description", "")).strip()[:300] or name,
            "params": {str(k): str(v)[:120] for k, v in params.items()}, "steps": clean, "agent": str(spec.get("agent") or "forge")[:40]}


def render(value, scope: dict):
    if isinstance(value, str):
        whole = SLOT.fullmatch(value.strip())
        if whole:
            return scope.get(whole.group(1), "")
        return SLOT.sub(lambda m: str(scope.get(m.group(1), "")), value)
    if isinstance(value, dict):
        return {k: render(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, scope) for v in value]
    return value


def risky(spec: dict, given: dict) -> bool:
    scope = {k: given.get(k, "") for k in spec["params"]}
    for index, step in enumerate(spec["steps"], 1):
        if registry.needs_confirm(step["tool"], render(step["args"], scope)):
            return True
        scope[f"s{index}"] = ""
    return False


async def execute(spec: dict, given: dict) -> str:
    from features.team import runner
    scope = {k: given.get(k, "") for k in spec["params"]}
    log = []
    for index, step in enumerate(spec["steps"], 1):
        result = await runner.run_as(step["tool"], render(step["args"], scope))
        scope[f"s{index}"] = result
        log.append(f"{index}. {step['tool']}: {result[:300]}")
    return "\n".join(log)


def register(spec: dict) -> None:
    async def run(**given) -> str:
        return await execute(spec, given)
    run.__name__ = spec["name"]
    run.__signature__ = inspect.Signature([inspect.Parameter(k, inspect.Parameter.KEYWORD_ONLY, default="", annotation=str) for k in spec["params"]])
    registry.TOOLS[spec["name"]] = {"name": spec["name"], "description": spec["description"] + " (strumento creato da Atena)", "args": spec["params"], "fn": run,
                                    "confirm": lambda args: risky(spec, args), "full_only": False, "agent": spec["agent"], "verify": None, "custom": True}
    CUSTOM[spec["name"]] = spec


def save(spec: dict) -> dict:
    spec = validate(spec)
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{spec['name']}.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
    register(spec)
    return spec


def remove(name: str) -> bool:
    if name not in CUSTOM:
        return False
    CUSTOM.pop(name)
    registry.TOOLS.pop(name, None)
    (DIR / f"{name}.json").unlink(missing_ok=True)
    return True


def load() -> int:
    count = 0
    for path in sorted(DIR.glob("*.json")) if DIR.is_dir() else []:
        try:
            register(validate(json.loads(path.read_text(encoding="utf-8"))))
            count += 1
        except (OSError, ValueError, TypeError):
            continue
    return count
