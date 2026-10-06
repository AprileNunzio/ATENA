import time

from features.desktop.desk import desk
from features.whiteboard import ocr, solver, teacher
from features.whiteboard.board import board

KEY = "lavagna"
TITLE_INK = "#ffd166"
RESULT_INK = "#7CFC9A"
FRESH = 900.0
LOOK_PROMPT = ("Questa è la lavagna su cui stiamo lavorando insieme. Leggi con attenzione tutto ciò che è "
               "scritto o disegnato. L'utente ti farà domande su qualsiasi materia (Matematica, Italiano, Geografia, Storia, Fisica, Chimica, ecc). "
               "Rispondi in italiano in modo chiaro, conciso e corretto, come un insegnante esperto, senza markdown.{question}")
EXPLAIN_SYSTEM = ("Sei un insegnante di scuola paziente e chiaro. Spieghi alla lavagna con frasi brevissime, una idea per riga. "
                  'Rispondi SOLO con JSON: {{"titolo": "titolo breve", "passi": ["riga 1", "riga 2"], "riassunto": "una frase da dire a voce"}}. '
                  "Massimo {rows} righe, ognuna sotto i 80 caratteri, in italiano, senza markdown né emoji.")
ROWS = 8

def is_open() -> bool:
    return any(i["key"] == KEY for i in desk.active())

def open_board() -> None:
    desk.scan()
    if KEY not in desk.widgets:
        raise LookupError("il widget della lavagna non è installato")
    if not is_open():
        board.reset()
    desk.show("lavagna", {}, key=KEY, priority=70, fullscreen=True)

def close_board() -> bool:
    opened = is_open()
    desk.hide(key=KEY)
    return opened

def set_fullscreen(on: bool) -> bool:
    return desk.fullscreen(KEY, on) is not None

def write(lines: list[str], title: str = "", ink: str = "", size: float = 42) -> int:
    if title:
        board.text(title, size=size + 10, ink=TITLE_INK)
    written = 0
    for line in lines:
        board.text(line, size=size, ink=ink or "#29e0ff")
        written += 1
    return written

def solve_on_board(text: str) -> dict:
    if not is_open():
        open_board()
    try:
        result = solver.solve(text)
        lines = result["lines"]
        for index, line in enumerate(lines):
            last = index == len(lines) - 1 and index > 0
            board.text(line, size=48 if last else 46 if index == 0 else 42, ink=RESULT_INK if last else TITLE_INK if index == 0 else "#29e0ff")
        board.say(result["speech"])
        return result
    except Exception as exc:
        if "divisione per zero" in str(exc).lower():
            raise
        return teacher.teach(text)

def auto_solve_board() -> dict | None:
    if not board.ai_enabled or not board.items:
        return None
    res = teacher.auto_evaluate()
    if res:
        return res
    last_item = board.items[-1]
    if last_item.get("by") == "atena":
        return None
    data = ocr.recognize_math(board.items, board.snapshot)
    if not data or not data.get("has_equals"):
        return None
    board.text(f" {data['result']}", x=data["x"], y=data["y"], size=data.get("size", 46), ink=RESULT_INK)
    board.say(data["speech"])
    return data

async def collaborate_math(question: str = "") -> dict:
    if not is_open():
        open_board()
    auto = auto_solve_board()
    if auto:
        return {"speech": auto["speech"], "lines": auto["lines"], "result": auto["result"]}
    data = ocr.recognize_math(board.items, board.snapshot)
    if data:
        lines = data["lines"]
        for index, line in enumerate(lines):
            last = index == len(lines) - 1 and index > 0
            board.text(line, size=48 if last else 46 if index == 0 else 42, ink=RESULT_INK if last else TITLE_INK if index == 0 else "#29e0ff")
        board.say(data["speech"])
        return {"speech": data["speech"], "lines": lines, "result": data["result"]}
    if board.snapshot and time.time() - board.snapshot_at <= FRESH:
        reply = await look(question or "risolvi i calcoli e le operazioni matematiche presenti sulla lavagna")
        return {"speech": reply, "lines": [reply], "result": reply}
    raise ValueError("non ho trovato calcoli o equazioni sulla lavagna: scrivi un'operazione")

async def explain_on_board(topic: str, lang: str = "it") -> dict:
    from features.whiteboard import teacher_kit
    if not is_open():
        open_board()
    try:
        return await teacher_kit.lesson(topic, lang)
    except ValueError:
        return await _explain_plain(topic)


async def _explain_plain(topic: str) -> dict:
    from features.brain.llm import generate
    reply = await generate(f"Spiega alla lavagna: {topic[:300]}", as_json=True, max_tokens=700, temperature=0.3, kind="chat",
                           system=EXPLAIN_SYSTEM.format(rows=ROWS), timeout=120)
    reply = reply if isinstance(reply, dict) else {}
    steps = [str(s) for s in (reply.get("passi") or []) if str(s).strip()][:ROWS]
    if not steps:
        raise ValueError("non sono riuscito a preparare la spiegazione")
    if not is_open():
        open_board()
    write(steps, str(reply.get("titolo") or topic)[:60])
    summary = str(reply.get("riassunto") or "Ho scritto la spiegazione alla lavagna.")[:240]
    board.say(summary)
    return {"title": reply.get("titolo") or topic, "steps": steps, "speech": summary}

async def look(question: str = "") -> str:
    from features.brain import sight
    if not board.snapshot or time.time() - board.snapshot_at > FRESH:
        raise ValueError("non ho ancora visto la lavagna: apri la lavagna e scrivi qualcosa")
    extra = f"\nDomanda dell'utente: {question[:300]}" if question else ""
    data, _ = await sight.look(board.snapshot, LOOK_PROMPT.format(question=extra), max_tokens=600)
    reply = str(data).strip()[:700]
    board.say(reply[:240])
    return reply
