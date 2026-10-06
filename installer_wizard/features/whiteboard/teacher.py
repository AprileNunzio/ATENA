import re
from features.whiteboard.board import COLUMNS, TOP, board
from features.whiteboard import ocr, shortcuts, solver

ERROR_INK = "#ff4d6a"
NOTE_INK = "#ffd166"
PERFECT_INK = "#29e0ff"
FAST_INK = "#7CFC9A"

DERIV_PATTERN = re.compile(r"(?:d/dx|derivata di|derivata)\s*[:\(]?\s*(?P<expr>.+)", re.I)
INTEG_PATTERN = re.compile(r"(?:integrale di|integrale|\u222b)\s*[:\(]?\s*(?P<expr>.+)", re.I)
LIMIT_PATTERN = re.compile(r"(?:limite per x\s*->\s*(?P<to>[-\d]+|inf|0)|limite di)\s*[:\(]?\s*(?P<expr>.+)", re.I)
EQUAT_PATTERN = re.compile(r"(?P<left>[^=]+)=(?P<right>[^=]+)")

def _clean_target(s: str) -> str:
    raw = s.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1].strip()
    elif raw.endswith(")"):
        raw = raw.rstrip(")")
    return raw

def _fallback_symbolic(clean: str) -> dict | None:
    d_m = DERIV_PATTERN.search(clean)
    if d_m:
        raw = _clean_target(d_m.group("expr"))
        if "x" in raw:
            parts = [p.strip() for p in raw.split("+")]
            diff_parts = []
            for p in parts:
                p_c = p.replace(" ", "")
                if "**" in p_c or "^" in p_c:
                    base, exp = re.split(r"\*\*|\^", p_c)
                    n = int(exp)
                    c_str = base.replace("*", "").replace("x", "")
                    coef = int(c_str) if c_str and c_str != "-" else (-1 if c_str == "-" else 1)
                    p_pow = f"*{coef * n}*x**{n-1}" if n > 2 else (f"{coef * 2}*x" if n == 2 else f"{coef}")
                    diff_parts.append(p_pow.lstrip("*"))
                elif "x" in p_c:
                    c_str = p_c.replace("*", "").replace("x", "")
                    coef = int(c_str) if c_str and c_str != "-" else (-1 if c_str == "-" else 1)
                    diff_parts.append(str(coef))
                else:
                    diff_parts.append("0")
            diff_clean = [dp for dp in diff_parts if dp != "0"]
            res = " + ".join(diff_clean) if diff_clean else "0"
            return {
                "kind": "derivative",
                "problem": f"d/dx ({raw})",
                "perfect_steps": [f"Derivata: d/dx ({raw})", "Applicando le regole di derivazione", f"= {res}"],
                "fast_rule": f"Regola rapida potenze/costanti: {res}",
                "result": res,
                "speech": f"La derivata rispetto a x è {res}."
            }
    i_m = INTEG_PATTERN.search(clean)
    if i_m:
        raw = _clean_target(i_m.group("expr"))
        if "x" in raw:
            parts = [p.strip() for p in raw.split("+")]
            integ_parts = []
            for p in parts:
                p_c = p.replace(" ", "")
                if "**" in p_c or "^" in p_c:
                    base, exp = re.split(r"\*\*|\^", p_c)
                    n = int(exp)
                    c_str = base.replace("*", "").replace("x", "")
                    coef = int(c_str) if c_str and c_str != "-" else (-1 if c_str == "-" else 1)
                    new_exp = n + 1
                    div = coef // new_exp if coef % new_exp == 0 else f"{coef}/{new_exp}"
                    integ_parts.append(f"{div}*x**{new_exp}" if div != 1 else f"x**{new_exp}")
            if integ_parts:
                res = " + ".join(integ_parts) + " + c"
                return {
                    "kind": "integral",
                    "problem": f"\u222b ({raw}) dx",
                    "perfect_steps": [f"Integrale indefinito di ({raw})", "Trovo la primitiva fondamentale", f"= {res}"],
                    "fast_rule": f"Formula immediata: {res}",
                    "result": res,
                    "speech": f"L'integrale indefinito è {res}."
                }
    l_m = LIMIT_PATTERN.search(clean)
    if l_m:
        raw = _clean_target(l_m.group("expr"))
        if "sin(x)/x" in raw.replace(" ", ""):
            return {
                "kind": "limit",
                "problem": f"lim (x -> 0) {raw}",
                "perfect_steps": ["Calcolo limite notevole", "Forma determinata:", "= 1"],
                "fast_rule": "Stima rapida dell'andamento: 1",
                "result": "1",
                "speech": "Il limite vale 1."
            }
    return None

def _symbolic_engine(expr_str: str) -> dict | None:
    clean = expr_str.replace("×", "*").replace("÷", "/").replace("^", "**").replace("−", "-").strip()
    try:
        import sympy as sp
        x = sp.Symbol("x")
        d_m = DERIV_PATTERN.search(clean)
        if d_m:
            target = sp.sympify(_clean_target(d_m.group("expr")))
            res = sp.diff(target, x)
            return {
                "kind": "derivative",
                "problem": f"d/dx ({target})",
                "perfect_steps": [f"Derivata: d/dx ({target})", "Applicando le regole di derivazione", f"= {res}"],
                "fast_rule": f"Regola rapida potenze/costanti: {res}",
                "result": str(res),
                "speech": f"La derivata rispetto a x è {res}."
            }
        i_m = INTEG_PATTERN.search(clean)
        if i_m:
            target = sp.sympify(_clean_target(i_m.group("expr")))
            res = sp.integrate(target, x)
            return {
                "kind": "integral",
                "problem": f"\u222b ({target}) dx",
                "perfect_steps": [f"Integrale indefinito di ({target})", "Trovo la primitiva fondamentale", f"= {res} + c"],
                "fast_rule": f"Formula immediata: {res} + c",
                "result": f"{res} + c",
                "speech": f"L'integrale indefinito è {res} più una costante c."
            }
        l_m = LIMIT_PATTERN.search(clean)
        if l_m:
            target = sp.sympify(_clean_target(l_m.group("expr")))
            to_val = 0 if not l_m.group("to") else sp.sympify(l_m.group("to"))
            res = sp.limit(target, x, to_val)
            return {
                "kind": "limit",
                "problem": f"lim (x -> {to_val}) {target}",
                "perfect_steps": [f"Calcolo limite per x tendente a {to_val}", "Forma determinata:", f"= {res}"],
                "fast_rule": f"Stima rapida dell'andamento: {res}",
                "result": str(res),
                "speech": f"Il limite vale {res}."
            }
        if "=" in clean and any(v in clean for v in ["x", "y"]):
            parts = clean.split("=")
            eq = sp.Eq(sp.sympify(parts[0]), sp.sympify(parts[1]))
            sols = sp.solve(eq, x)
            sol_str = ", ".join(str(s) for s in sols)
            return {
                "kind": "equation",
                "problem": expr_str,
                "perfect_steps": [f"Equazione: {parts[0].strip()} = {parts[1].strip()}", "Porto tutto a sinistra ed esplicito", f"Soluzioni: x = {sol_str}"],
                "fast_rule": f"Scorciatoia algebrica diretta: x = {sol_str}",
                "result": sol_str,
                "speech": f"L'equazione ha come soluzione x uguale a {sol_str}."
            }
        parsed = sp.sympify(clean)
        res = sp.simplify(parsed)
        return {
            "kind": "algebra",
            "problem": expr_str,
            "perfect_steps": [f"Espressione: {expr_str}", "Semplificazione formale", f"= {res}"],
            "fast_rule": f"Calcolo rapido: {res}",
            "result": str(res),
            "speech": f"L'espressione semplificata è {res}."
        }
    except Exception:
        return _fallback_symbolic(clean)

def detect_student_error(raw_expr: str) -> dict | None:
    if "=" not in raw_expr:
        return None
    parts = raw_expr.split("=")
    if len(parts) != 2:
        return None
    lhs, rhs = parts[0].strip(), parts[1].strip()
    if not lhs or not rhs:
        return None
    if not any(c.isdigit() for c in rhs):
        return None
    try:
        sol = solver.solve(lhs)
        actual = str(sol["result"]).strip()
        expected_clean = re.sub(r"[^\d,\.\-]", "", actual).replace(",", ".")
        rhs_clean = re.sub(r"[^\d,\.\-]", "", rhs).replace(",", ".")
        if expected_clean and rhs_clean and float(expected_clean) != float(rhs_clean):
            return {
                "has_error": True,
                "claimed": rhs,
                "expected": actual,
                "expression": lhs,
                "hint": f"⚠️ Attento: {lhs} fa {actual}, non {rhs}!"
            }
    except Exception:
        pass
    return None

LETTERS = re.compile(r"[a-z\u222b]", re.I)
TIP_SIZE = 28
STEP_SIZE = 30
LINE_GAP = 1.35


def _box(text: str, size: float) -> tuple[float, float]:
    return len(text) * size * 0.52, size * 1.1


def _block(rows: list[tuple[str, float, str]], line: list | None) -> None:
    if not rows:
        return
    width = max(_box(text, size)[0] for text, size, _ in rows)
    height = sum(size * LINE_GAP for _, size, _ in rows)
    anchor = (line[0], line[3] + 18.0) if line else (COLUMNS[0], TOP)
    spot = (board.free_spot(*anchor, width, height) or board.free_spot(COLUMNS[1], TOP, width, height)
            or board.free_spot(COLUMNS[0], TOP, width, height))
    if spot is None:
        board.add_page()
        spot = (COLUMNS[0], TOP)
    x, y = spot
    for text, size, ink in rows:
        board.text(text, x=x, y=y, size=size, ink=ink)
        y += size * LINE_GAP


def _answer(text: str, x, y, size: float, ink: str, line: list | None) -> None:
    if x is not None and y is not None:
        w, h = _box(text, size)
        if board.free_spot(x, y, w, h) == (x, y):
            board.text(text, x=x, y=y, size=size, ink=ink)
            return
    _block([(text, size, ink)], line)


def _tip_rows(tip: str) -> list[tuple[str, float, str]]:
    if not tip:
        return []
    wrapped = board.wrap(f"💡 Metodo perfetto: {tip}", TIP_SIZE, 900)
    return [(row, TIP_SIZE, PERFECT_INK) for row in wrapped[:4]]


def _line_of(x, y, size: float, line: list | None) -> list | None:
    if line:
        return list(line)
    if x is None or y is None:
        return None
    return [x, y, x, y + size * 1.1]


def teach(expression: str, x: float | None = None, y: float | None = None, line: list | None = None,
          size: float = 46.0) -> dict:
    anchor = _line_of(x, y, size, line)
    err = detect_student_error(expression)
    if err and err.get("has_error"):
        return _correct(err, anchor, size)
    clean_expr = expression.strip().rstrip("=").strip()
    if LETTERS.search(clean_expr):
        sym = _symbolic_engine(expression)
        if sym:
            return _symbolic(sym, x, y, anchor, size)
    sol = solver.solve(clean_expr)
    _answer(str(sol["result"]), x, y, size, FAST_INK, anchor)
    tip = shortcuts.arithmetic(solver.normalize(clean_expr, False))
    steps = [(f"  {row}", STEP_SIZE, NOTE_INK) for row in sol["lines"]] if len(sol["lines"]) > 2 else []
    _block(steps + _tip_rows(tip), anchor)
    speech = f"{clean_expr} fa {sol['result']}." + (" Ti ho lasciato il metodo perfetto per farlo più in fretta." if tip else "")
    board.say(speech)
    return {"error_detected": False, "result": str(sol["result"]), "speech": speech, "lines": sol["lines"], "perfect": tip}


def _correct(err: dict, anchor: list | None, size: float) -> dict:
    sol = solver.solve(err["expression"])
    if anchor:
        board.underline(anchor[0], anchor[3] + 6.0, max(anchor[2], anchor[0] + 120.0), ink=ERROR_INK, width=4)
    tip = shortcuts.arithmetic(solver.normalize(err["expression"], False))
    _block([(err["hint"], 32, NOTE_INK)] + _tip_rows(tip), anchor)
    speech = f"Attenzione: {err['expression']} fa {sol['result']}, non {err['claimed']}. Ti ho segnato la correzione."
    board.say(speech)
    return {"error_detected": True, "correction": sol["result"], "speech": speech, "perfect": tip,
            "lines": [err["hint"]], "result": str(sol["result"])}


def _symbolic(sym: dict, x, y, anchor: list | None, size: float) -> dict:
    _answer(f"= {sym['result']}" if sym["kind"] != "equation" else str(sym["result"]), x, y, size, FAST_INK, anchor)
    steps = [(f"  {row}", STEP_SIZE, NOTE_INK) for row in sym["perfect_steps"]]
    tip = shortcuts.symbolic(sym["kind"])
    _block(steps + _tip_rows(tip), anchor)
    board.say(sym["speech"])
    return {"error_detected": False, "result": sym["result"], "speech": sym["speech"], "steps": sym["perfect_steps"],
            "perfect": tip, "lines": sym["perfect_steps"]}


def auto_evaluate() -> dict | None:
    if not board.ai_enabled or not board.items:
        return None
    last_item = board.items[-1]
    if last_item.get("by") == "atena":
        return None
    data = ocr.recognize_math(board.items, board.snapshot)
    if not data or not data.get("has_equals"):
        return None
    expr = data.get("expression") or data.get("clean")
    if not expr:
        return None
    if not re.search(r"[\+\-\*/\=\^\(\)\u222bx]", expr.lower()) and not re.search(r"\b(derivata|integrale|limite|sin|cos|tan|log|ln)\b", expr, re.I):
        return None
    try:
        return teach(expr, data.get("x"), data.get("y"), data.get("line"), data.get("size", 46.0))
    except Exception:
        return None
