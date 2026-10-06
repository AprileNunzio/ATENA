import asyncio
import re
import time

from state import store

from features.vision import ir_configure, ir_emitter, webcams as cams

MAX_SKIPS = 4
VERIFY_SECONDS = 25
PROMPT = re.compile(r"(yes\s*/\s*no|y\s*/\s*n|\[y\]|\(y\)|\?\s*$)", re.I)
BLIND = ("Unable to read a frame", "can't open camera", "can't ope")
state = {"running": False, "stop": False, "stage": "", "device": "", "attempt": 0, "result": "", "log": []}


def note(text: str) -> None:
    state["stage"] = text
    state["log"] = (state["log"] + [text])[-12:]


def view() -> dict:
    return {**state, "log": list(state["log"])}


def is_prompt(output: str) -> bool:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return bool(lines) and bool(PROMPT.search(lines[-1])) and not lines[-1].startswith(">")


def candidates(snapshot: dict) -> list[dict]:
    selected = (snapshot.get("selected") or {}).get("ir")
    found = [{"device": d["ir"], "mode": d.get("ir_mode")} for d in snapshot.get("devices", []) if d.get("ir")]
    found.sort(key=lambda c: c["device"] != selected)
    seen, unique = set(), []
    for item in found:
        if item["device"] not in seen:
            seen.add(item["device"])
            unique.append(item)
    return unique


def skipper(skips: int):
    count = {"asked": 0, "tail": ""}

    def respond(output: str) -> str | None:
        if not is_prompt(output):
            return None
        tail = output.strip().splitlines()[-1]
        if tail == count["tail"]:
            return None
        count["tail"] = tail
        count["asked"] += 1
        return "n" if count["asked"] <= skips else "y"
    return respond


async def wait_session() -> None:
    while ir_configure.session["running"]:
        await asyncio.sleep(1)


async def lit() -> bool:
    deadline = time.time() + VERIFY_SECONDS
    while time.time() < deadline:
        await asyncio.sleep(3)
        if cams.read_json(cams.IR_STATUS_FILE).get("state") == "ok":
            return True
    return False


async def attempt(tool: str, item: dict, skips: int) -> str:
    state.update(device=item["device"], attempt=skips + 1)
    note(f"{item['device']}: prova {skips + 1} di {MAX_SKIPS + 1}")
    await ir_configure.start(tool, item["device"], item["mode"], responder=skipper(skips))
    await wait_session()
    output = ir_configure.session["output"]
    if any(marker in output for marker in BLIND):
        return "blind"
    if not ir_configure.session["result"].startswith("completata"):
        return "failed"
    note(f"{item['device']}: verifica che la luce infrarossa sia accesa")
    return "ok" if await lit() else "dark"


async def execute() -> str:
    if not ir_emitter.tool_path():
        note("installo lo strumento verificato")
        await ir_emitter.install()
    snapshot = await cams.webcams.refresh(force=True)
    options = candidates(snapshot)
    if not options:
        return "nessun sensore infrarosso trovato"
    tool = ir_emitter.tool_path()
    for item in options:
        for skips in range(MAX_SKIPS + 1):
            if state["stop"]:
                return "interrotta dall'utente"
            outcome = await attempt(tool, item, skips)
            if outcome == "ok":
                await ir_emitter.enable_service()
                return f"emettitore acceso e attivato a ogni avvio su {item['device']}"
            if outcome in ("blind", "failed"):
                note(f"{item['device']}: nodo non utilizzabile, passo al successivo")
                break
    return "nessuna combinazione ha acceso l'emettitore: la webcam potrebbe non averne uno controllabile"


async def run() -> None:
    try:
        state["result"] = await execute()
    except (RuntimeError, ValueError, OSError) as exc:
        state["result"] = f"interrotta: {exc}"
    except Exception as exc:
        state["result"] = f"errore: {exc}"
    state["running"] = False
    note(state["result"])
    store.event("INFO", f"Configurazione automatica dell'infrarosso: {state['result']}", "vision")


def start() -> dict:
    if state["running"] or ir_configure.session["running"]:
        raise RuntimeError("Configurazione già in corso")
    state.update(running=True, stop=False, stage="avvio", device="", attempt=0, result="", log=[])
    asyncio.get_running_loop().create_task(run())
    return view()


def cancel() -> dict:
    state["stop"] = True
    ir_configure.cancel()
    return view()
