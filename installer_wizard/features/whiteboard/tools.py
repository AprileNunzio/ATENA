from functools import partial

from features.agent.registry import tool
from features.whiteboard import service
from features.whiteboard.board import HEIGHT, WIDTH, board

lavagna = partial(tool, agent="whiteboard")


@lavagna("board_open", "apre la lavagna sul display, sempre vuota e a tutto schermo: Atena e l'utente scrivono e disegnano insieme", {})
async def board_open() -> str:
    service.open_board()
    return "lavagna aperta, vuota e a tutto schermo"


@lavagna("board_close", "chiude la lavagna (il contenuto resta salvato)", {})
async def board_close() -> str:
    return "lavagna chiusa" if service.close_board() else "la lavagna non era aperta"


@lavagna("board_write", "scrive testo sulla lavagna; senza posizione si impagina e va a capo da sola, con x (0-%d) e y (0-%d) lo mette dove vuoi" % (WIDTH, HEIGHT),
         {"text": "testo", "x": "posizione orizzontale", "y": "posizione verticale", "size": "altezza del carattere 16-140", "color": "#rrggbb"})
async def board_write(text: str, x: float | None = None, y: float | None = None, size: float = 42, color: str = "") -> str:
    if not service.is_open():
        service.open_board()
    if x in (None, "") or y in (None, ""):
        board.paragraph(text, size, color or "#29e0ff")
    else:
        board.text(text, x, y, size, color or "#29e0ff")
    return "scritto alla lavagna"


@lavagna("board_draw", "disegna sulla lavagna una figura: line, arrow, rect o ellipse, tra due punti (x1,y1)-(x2,y2) su una lavagna di %d×%d" % (WIDTH, HEIGHT),
         {"shape": "line|arrow|rect|ellipse", "x1": "x iniziale", "y1": "y iniziale", "x2": "x finale", "y2": "y finale", "color": "#rrggbb"})
async def board_draw(shape: str, x1: float, y1: float, x2: float, y2: float, color: str = "") -> str:
    if not service.is_open():
        service.open_board()
    board.shape(shape, x1, y1, x2, y2, color or "#29e0ff")
    return f"{shape} disegnata"


@lavagna("board_solve", "risolve un calcolo o un'equazione di primo grado e scrive alla lavagna tutti i passaggi come a scuola (es. «12 x (3 + 4)», «2x + 3 = 11»)",
         {"expression": "calcolo o equazione"})
async def board_solve(expression: str) -> str:
    result = service.solve_on_board(expression)
    return "passaggi scritti alla lavagna: " + " ".join(result["lines"]) + f" → {result['result']}"


@lavagna("board_look", "guarda la lavagna come un insegnante: legge ciò che c'è scritto e disegnato e verifica calcoli e ragionamenti", {"question": "domanda facoltativa"})
async def board_look(question: str = "") -> str:
    return await service.look(question)


@lavagna("board_clear", "cancella tutto il contenuto della lavagna", {}, confirm=True)
async def board_clear() -> str:
    return f"lavagna pulita ({board.clear()} elementi cancellati)"


def _ready() -> None:
    if not service.is_open():
        service.open_board()


def _list(value) -> list:
    if isinstance(value, list):
        return value
    import json
    try:
        parsed = json.loads(str(value))
    except ValueError:
        return [v.strip() for v in str(value).split(",") if v.strip()]
    return parsed if isinstance(parsed, list) else [parsed]


@lavagna("board_lesson", "prepara alla lavagna una lezione completa e impaginata su qualsiasi materia (matematica, fisica, chimica, lingue, storia…) con passaggi, formule, grafici, tabelle, riquadri e immagini",
         {"topic": "argomento", "subject": "math|physics|chemistry|science|history|geography|language|literature|other", "lang": "lingua (it, en…)"})
async def board_lesson(topic: str, subject: str = "other", lang: str = "it") -> str:
    from features.whiteboard import teacher_kit
    _ready()
    result = await teacher_kit.lesson(topic, lang, subject)
    return f"lezione «{result['title']}» alla lavagna ({result['blocks']} blocchi)"


@lavagna("board_callout", "aggiunge alla lavagna un riquadro a comparsa: info, tip, warning, definition, formula o example",
         {"kind": "info|tip|warning|definition|formula|example", "title": "titolo", "text": "testo"})
async def board_callout(kind: str, title: str, text: str) -> str:
    _ready()
    board.callout(kind, title, text)
    return "riquadro aggiunto"


@lavagna("board_mark", "evidenzia, sottolinea, cerchia, riquadra o barra le ultime righe scritte",
         {"style": "highlight|underline|wavy|circle|box|strike", "count": "quante righe (1-10)"})
async def board_mark(style: str = "highlight", count: int = 1) -> str:
    from features.whiteboard import teacher_kit
    return f"{teacher_kit.highlight_last(style, int(count or 1))} elementi segnati"


@lavagna("board_plot", "disegna il grafico di una o più funzioni di x con assi e griglia (es. «x^2», «sin(x)», «1/x»)",
         {"functions": "lista di funzioni", "xmin": "inizio asse x", "xmax": "fine asse x", "title": "titolo"})
async def board_plot(functions, xmin: float = -10, xmax: float = 10, title: str = "") -> str:
    from features.whiteboard import teacher_kit
    _ready()
    teacher_kit.plot_functions([str(f) for f in _list(functions)], float(xmin), float(xmax), title)
    return "grafico disegnato"


@lavagna("board_chart", "disegna un grafico a barre, a linee o a torta con etichette e valori",
         {"kind": "bar|line|pie", "labels": "lista di etichette", "values": "lista di numeri", "title": "titolo"})
async def board_chart(kind: str, labels, values, title: str = "") -> str:
    _ready()
    board.chart(kind, _list(labels), _list(values), title)
    return "grafico disegnato"


@lavagna("board_formula", "scrive una formula matematica impaginata (frazioni, potenze, radici) oppure calcola derivata, integrale o limite con i passaggi",
         {"expression": "espressione in x", "operation": "show|derivative|integral|limit", "point": "punto del limite (es. 0, oo)"})
async def board_formula(expression: str, operation: str = "show", point: str = "0") -> str:
    from features.whiteboard import teacher_kit
    _ready()
    if operation in ("derivative", "integral", "limit"):
        return "risultato: " + teacher_kit.calculus(operation, expression, point)["plain"]
    teacher_kit.formula(expression)
    return "formula scritta"


@lavagna("board_table", "scrive una tabella allineata (traduzioni, coniugazioni, dati, confronti)",
         {"header": "lista delle intestazioni", "rows": "lista di righe (liste)", "title": "titolo"})
async def board_table(header, rows, title: str = "") -> str:
    _ready()
    board.table(_list(header), _list(rows), title)
    return "tabella scritta"


@lavagna("board_image", "mostra alla lavagna un'immagine illustrativa presa da Wikipedia", {"topic": "titolo della voce", "lang": "lingua di Wikipedia"})
async def board_image(topic: str, lang: str = "it") -> str:
    from features.whiteboard import teacher_kit
    _ready()
    return "immagine aggiunta" if await teacher_kit.image(topic, lang) else "nessuna immagine adatta trovata"


@lavagna("board_chemistry", "chimica alla lavagna: bilancia una reazione oppure calcola la massa molare di un composto",
         {"reaction": "es. «C3H8 + O2 -> CO2 + H2O»", "formula": "es. «H2SO4»"})
async def board_chemistry(reaction: str = "", formula: str = "") -> str:
    from features.whiteboard import teacher_kit
    _ready()
    if reaction:
        return "reazione bilanciata: " + teacher_kit.balance(reaction)["equation"]
    data = teacher_kit.molar_mass(formula)
    return f"massa molare {data['formula']} = {data['total']} g/mol"


@lavagna("board_physics", "fisica alla lavagna: risolve una formula con le unità di misura (es. F = m*a con m = 2 kg e a = 3 m/s^2)",
         {"formula": "formula", "known": "oggetto JSON {nome: \"valore unità\"}", "target": "grandezza da trovare"})
async def board_physics(formula: str, known, target: str) -> str:
    import json
    from features.whiteboard import teacher_kit
    _ready()
    values = known if isinstance(known, dict) else json.loads(str(known))
    return teacher_kit.physics(formula, {str(k): str(v) for k, v in values.items()}, target)["result"]


@lavagna("board_language", "scheda di lingua alla lavagna: traduzione, coniugazione o declinazione con tabella e note", {"text": "parola o frase", "lang": "lingua della spiegazione"})
async def board_language(text: str, lang: str = "it") -> str:
    from features.whiteboard import teacher_kit
    _ready()
    return (await teacher_kit.language_card(text, lang))["title"]


@lavagna("board_new_page", "apre una nuova pagina pulita della lavagna", {})
async def board_new_page() -> str:
    return f"pagina {board.add_page() + 1}"
