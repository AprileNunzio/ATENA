import re

from config import env_get
from features.brain.llm import BrainUnavailable
from features.whiteboard import service, solver
from features.whiteboard.board import board

FACE = {"mode": "face"}
BOARD = re.compile(r"\b(?:la |alla |sulla |dalla |una |nella |sula )?lavagna\b")
OPEN = re.compile(r"\b(apri|aprimi|mostra|mostrami|accendi|prepara|preparami|metti|portami|fammi vedere|voglio|usiamo|usa)\b")
CLOSE = re.compile(r"\b(chiudi|togli|nascondi|spegni|rimuovi|basta con)\b")
FULL = re.compile(r"\b(a )?(tutto|pieno) schermo\b|\bschermo intero\b|\bfullscreen\b|\bingrandisci\b|\bmassimizza\b")
NORMAL = re.compile(r"\b(schermo normale|rimpicciolisci|riduci|esci dal tutto schermo)\b")
CLEAR = re.compile(r"\b(cancella|pulisci|svuota|ripulisci|azzera|ricomincia|nuova)\b")
WRITE = re.compile(r"\b(?:scrivi|scrivimi|annota|appunta|segna)\b(?: (?:sulla lavagna|alla lavagna|qui))?\s*[:,]?\s*(?P<rest>.+)$")
SOLVE = re.compile(r"\b(calcola|calcoliamo|risolvi|risolviamo|quanto fa|quanto vale|fai il conto|fai il calcolo|svolgi|facciamo|collaboriamo|aiutami a risolver|risolvi quello)\b")
EXPLAIN = re.compile(r"\b(spiega|spiegami|spieghiamo|ragioniamo|ragiona|dimostra|dimostrami|mostrami come|fammi capire|rappresenta)\b(?P<rest>.*)$")
LOOK = re.compile(r"\b(cosa ho scritto|che cosa ho scritto|leggi|guarda|controlla|correggi|verifica|e giusto|è giusto|ho sbagliato|va bene cosi)\b")
UNDO = re.compile(r"\b(annulla|torna indietro|cancella (?:l'ultim\w+|l ultim\w+))\b")
MATH = re.compile(r"\d")
MATH_COLLAB = re.compile(r"\b(matematica|calcoli|equazioni|operazioni|algebra|esercizi)\b")
COLLAB = re.compile(r"\b(lavoriamo|collaboriamo|studiamo|facciamo insieme|risolviamo insieme|aiutami con|aiutami a fare)\b")
STOP = re.compile(r"\b(?:atena|athena|per favore|sulla lavagna|alla lavagna|la lavagna|lavagna|sul quaderno|con i passaggi|passo passo|passaggi|"
                  r"calcola|calcoliamo|risolvi|risolviamo|quanto fa|quanto vale|fai il conto|svolgi|facciamo|l'equazione|equazione|"
                  r"il calcolo|calcolo|operazione|espressione|questa|questo|seguente|scrivi|scrivimi|e)\b")

LEAD = re.compile(r"^(?:e |ed |poi |quindi |allora |invece )?(?:adesso |ora )?(?:fa |fanno |viene |vale )?")
WORD_OPS = re.compile(r"\b(?:per|piu|meno|diviso|fratto|alla|elevato a|volte)\b")

def bare_math(t: str) -> str:
    body = LEAD.sub("", t, count=1).strip()
    rest = WORD_OPS.sub(" ", body)
    if not re.fullmatch(r"[\d\s+*/x×÷:^().,=-]+", rest) or not re.search(r"\d", rest):
        return ""
    operator = rest != body or re.search(r"[+*/×÷:^=]|\d\s*-\s*\d|\d\s*x\s*\d|\dx", rest)
    return body if operator else ""

PLOT = re.compile(r"\b(grafico|traccia|plotta|disegna la funzione|studia la funzione)\b")
DERIVATIVE = re.compile(r"\bderivata\b")
INTEGRAL = re.compile(r"\bintegrale\b")
LIMIT = re.compile(r"\blimite\b")
MOLAR = re.compile(r"\b(massa molare|peso molecolare)\b")
BALANCE = re.compile(r"\bbilancia\b")
IMAGE = re.compile(r"\b(?:immagine|foto|figura|disegno) (?:di |del |della |dello |dei |degli |delle |dell )(?P<topic>.+)$")
MARK = {"evidenzia": "highlight", "sottolinea": "underline", "cerchia": "circle", "barra": "strike", "riquadra": "box"}
LANGUAGE = re.compile(r"\b(coniuga|traduci|declina|come si dice)\b")
FORMULA_TOKEN = re.compile(r"(?:\d*(?:[A-Z][a-z]?\d*|\([A-Za-z0-9]+\)\d*)+(?:[·.*]\d*(?:[A-Z][a-z]?\d*|\([A-Za-z0-9]+\)\d*)+)?)")
SPECIES = r"\d*(?:[A-Z][a-z]?\d*|\([A-Za-z0-9]+\)\d*)+(?:·\d*(?:[A-Z][a-z]?\d*)+)?"
REACTION = re.compile(rf"{SPECIES}(?:\s*\+\s*{SPECIES})*\s*(?:->|→|=)\s*{SPECIES}(?:\s*\+\s*{SPECIES})*")
MATH_TAIL = re.compile(r"(?:di|della funzione|della|del|per)\s+(?P<expr>.+)$")
RANGE = re.compile(r"\bda\s+(-?\d+(?:[.,]\d+)?)\s+a\s+(-?\d+(?:[.,]\d+)?)\b")


def _expression(text: str) -> str:
    body = RANGE.sub("", text)
    m = MATH_TAIL.search(body)
    expr = (m.group("expr") if m else body).strip(" .?!:")
    expr = re.sub(r"^(?:y\s*=\s*|f\(x\)\s*=\s*)", "", expr)
    return re.sub(r"\b(?:alla|sulla) lavagna\b|\bper favore\b|\b(?:atena|athena)\b", "", expr).strip(" .?!:,")


async def science(text: str, t: str) -> tuple[str, dict] | None:
    from features.whiteboard import science as sci
    from features.whiteboard import teacher_kit as kit
    try:
        if MOLAR.search(t):
            tokens = [x for x in FORMULA_TOKEN.findall(text) if re.search(r"[A-Z]", x)]
            if not tokens:
                return None
            data = kit.molar_mass(tokens[-1])
            return f"La massa molare di {data['formula']} è {data['total']} grammi per mole.", FACE
        if BALANCE.search(t):
            m = REACTION.search(text)
            if not m:
                return None
            data = kit.balance(m.group(0))
            return f"Reazione bilanciata: {data['equation']}.", FACE
        if DERIVATIVE.search(t) or INTEGRAL.search(t):
            kind = "derivative" if DERIVATIVE.search(t) else "integral"
            data = kit.calculus(kind, _expression(t))
            return f"Il risultato è {data['plain']}. Ho scritto i passaggi alla lavagna.", FACE
        if LIMIT.search(t):
            m = re.search(r"(?:per )?x che tende a (\S+)", t)
            point = (m.group(1) if m else "0").replace("infinito", "oo")
            data = kit.calculus("limit", _expression(re.sub(r"(?:per )?x che tende a \S+", "", t)), point)
            return f"Il limite vale {data['plain']}.", FACE
        if PLOT.search(t):
            r = RANGE.search(t)
            low, high = (float(r.group(1).replace(",", ".")), float(r.group(2).replace(",", "."))) if r else (-10.0, 10.0)
            functions = [f.strip() for f in re.split(r"\s+e\s+|;", _expression(t)) if f.strip()][:4]
            kit.plot_functions(functions, low, high)
            return "Ecco il grafico alla lavagna.", FACE
        word = next((w for w in MARK if re.search(rf"\b{w}\b", t)), None)
        if word:
            count = 3 if re.search(r"\b(ultime|tutto|tutte)\b", t) else 1
            done = kit.highlight_last(MARK[word], count)
            return ("Fatto." if done else "Non c'è ancora niente da segnare."), FACE
        m = IMAGE.search(t)
        if m:
            topic = re.sub(r"\b(?:alla|sulla) lavagna\b", "", m.group("topic")).strip(" .?!")
            added = await kit.image(topic, "it")
            return ("Ecco un'immagine alla lavagna." if added else f"Non ho trovato un'immagine adatta per {topic}."), FACE
        if LANGUAGE.search(t):
            data = await kit.language_card(text, "it")
            return (data["speech"] or "Ho preparato la scheda alla lavagna."), FACE
    except sci.ScienceError:
        return "Non riesco a interpretare l'espressione: prova a scriverla in un altro modo.", FACE
    except BrainUnavailable as exc:
        return f"Il mio cervello non è raggiungibile in questo momento: {exc}", FACE
    except ValueError as exc:
        return f"Non ci riesco: {exc}.", FACE
    return None


def enabled() -> bool:
    return env_get("ATENA_WHITEBOARD", "1") != "0"

def plain(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower().replace("à", "a").replace("è", "e").replace("é", "e").replace("ì", "i").replace("ò", "o").replace("ù", "u")).strip(" .?!")

def expression_of(text: str) -> str:
    return re.sub(r"\s+", " ", STOP.sub(" ", text.lower())).strip(" .?!:,")

def writing(text: str) -> tuple[str, dict]:
    content = WRITE.search(text).group("rest").strip(" .")
    content = re.sub(r"^(?:sulla lavagna|alla lavagna|che|questo|quanto segue)\s*[:,]?\s*", "", content).strip()
    if not content:
        raise LookupError
    if not service.is_open():
        service.open_board()
    board.text(content, size=44)
    return "Scritto alla lavagna.", FACE

async def answer(text: str) -> tuple[str, dict]:
    if not enabled():
        raise LookupError
    t = plain(text)
    on_board, opened = bool(BOARD.search(t)), service.is_open()
    is_collab = bool(COLLAB.search(t) and MATH_COLLAB.search(t))
    if not on_board and not opened and not is_collab:
        raise LookupError
    if on_board and CLOSE.search(t) and not (SOLVE.search(t) or EXPLAIN.search(t)):
        return ("Ho chiuso la lavagna." if service.close_board() else "La lavagna non era aperta."), FACE
    if on_board and CLEAR.search(t):
        if not opened:
            raise LookupError
        board.clear()
        return "Lavagna pulita.", FACE
    if opened and UNDO.search(t):
        return ("Ho cancellato l'ultima cosa che hai scritto." if board.undo("user") or board.undo("atena") else "Non c'è niente da annullare."), FACE
    if (on_board or is_collab) and (OPEN.search(t) or is_collab) and not (SOLVE.search(t) or EXPLAIN.search(t)):
        service.open_board()
        if MATH_COLLAB.search(t) or is_collab:
            return "Ecco la lavagna a tutto schermo: lavoriamo insieme sulla matematica! Scrivi pure un calcolo o un'operazione e la risolveremo insieme.", FACE
        return "Ecco la lavagna a tutto schermo: scrivi pure, io ti seguo.", FACE
    if opened and FULL.search(t) and not on_board:
        service.set_fullscreen(True)
        return "Lavagna a tutto schermo.", FACE
    if opened and NORMAL.search(t):
        service.set_fullscreen(False)
        return "Lavagna alla dimensione normale.", FACE
    if on_board or opened:
        rich = await science(text, t)
        if rich:
            if not service.is_open():
                service.open_board()
            return rich
    follow = bare_math(t) if opened and not on_board else ""
    if (on_board or opened) and ((SOLVE.search(t) and MATH.search(t)) or follow):
        try:
            result = service.solve_on_board(follow or expression_of(t))
        except ValueError as exc:
            return f"Non riesco a risolverlo: {exc}.", FACE
        return f"{result['speech']} Ho scritto i passaggi alla lavagna.", FACE
    if (on_board or opened) and SOLVE.search(t) and not MATH.search(t):
        try:
            res = await service.collaborate_math(text)
            return f"{res['speech']} Ho scritto i passaggi alla lavagna.", FACE
        except BrainUnavailable as exc:
            return f"Il mio cervello non è raggiungibile in questo momento: {exc}", FACE
        except ValueError as exc:
            return f"{exc}.", FACE
    if (on_board or opened) and EXPLAIN.search(t):
        topic = expression_of(EXPLAIN.search(t).group("rest")) or expression_of(t)
        try:
            return (await service.explain_on_board(topic))["speech"], FACE
        except BrainUnavailable as exc:
            return f"Il mio cervello non è raggiungibile in questo momento: {exc}", FACE
        except ValueError as exc:
            return f"{exc}.", FACE
    if opened and WRITE.search(t):
        return writing(text.lower())
    if (on_board or opened) and LOOK.search(t):
        try:
            res = await service.collaborate_math(text)
            return f"{res['speech']} Ho verificato il contenuto alla lavagna.", FACE
        except Exception:
            pass
        try:
            return await service.look(text), FACE
        except BrainUnavailable as exc:
            return f"Non riesco a guardare la lavagna in questo momento: {exc}", FACE
        except ValueError as exc:
            return f"{exc}.", FACE
    raise LookupError

__all__ = ["answer", "solver"]
