import math
import re
from fractions import Fraction

import sympy as sp
from sympy.parsing.sympy_parser import convert_xor, implicit_multiplication_application, parse_expr, standard_transformations

MAX_EXPR = 160
SAMPLES = 240
ALLOWED = re.compile(r"^[0-9a-zA-Z+\-*/^().,=\s_πeE√|]+$")
FUNCTIONS = {name: getattr(sp, name) for name in ("sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "exp", "log",
                                                  "sqrt", "Abs", "floor", "ceiling", "factorial", "pi", "E")}
FUNCTIONS.update({"ln": sp.log, "abs": sp.Abs, "sen": sp.sin, "tg": sp.tan, "arcsin": sp.asin, "arccos": sp.acos, "arctan": sp.atan,
                  "e": sp.E, "π": sp.pi})
SYMBOLS = {name: sp.Symbol(name, real=True) for name in "xytnkabcz"}
TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)
SUPERSCRIPT = str.maketrans("0123456789+-n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ")
SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


class ScienceError(ValueError):
    pass


def parse(text: str) -> sp.Expr:
    raw = str(text or "").strip().replace("√", "sqrt").replace("π", "pi").replace("·", "*").replace("×", "*").replace("÷", "/")
    raw = raw.replace(",", ".") if raw.count(",") and "(" not in raw else raw
    if not raw or len(raw) > MAX_EXPR or not ALLOWED.match(raw) or "__" in raw:
        raise ScienceError("whiteboard.error.expression")
    if re.search(r"\*\*\s*\d{3,}|\^\s*\d{3,}", raw):
        raise ScienceError("whiteboard.error.expression")
    try:
        expr = parse_expr(raw, local_dict={**FUNCTIONS, **SYMBOLS}, transformations=TRANSFORMS, evaluate=True)
    except Exception:
        raise ScienceError("whiteboard.error.expression")
    if not isinstance(expr, sp.Basic):
        raise ScienceError("whiteboard.error.expression")
    return expr


def pretty(expr) -> list[str]:
    return sp.pretty(expr, use_unicode=True, wrap_line=False).splitlines()


def _finite(value) -> float | None:
    try:
        number = complex(value)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None
    if abs(number.imag) > 1e-9 or not math.isfinite(number.real):
        return None
    return number.real


def sample(text: str, xmin: float = -10.0, xmax: float = 10.0, samples: int = SAMPLES) -> dict:
    if not (-1e6 <= xmin < xmax <= 1e6):
        raise ScienceError("whiteboard.error.range")
    expr = parse(text)
    x = SYMBOLS["x"]
    if expr.free_symbols - {x}:
        raise ScienceError("whiteboard.error.variables")
    fn = sp.lambdify(x, expr, modules=["math", {"Abs": abs}])
    step = (xmax - xmin) / (samples - 1)
    points: list = []
    for i in range(samples):
        xv = xmin + i * step
        try:
            yv = _finite(fn(xv))
        except (ValueError, ZeroDivisionError, OverflowError, TypeError):
            yv = None
        points.append([round(xv, 5), None if yv is None else round(yv, 6)])
    ys = sorted(p[1] for p in points if p[1] is not None)
    if not ys:
        raise ScienceError("whiteboard.error.undefined")
    low, high = ys[int(len(ys) * 0.04)], ys[min(len(ys) - 1, int(len(ys) * 0.96))]
    span = (high - low) or 1.0
    jump = span * 3
    for i in range(1, len(points)):
        a, b = points[i - 1][1], points[i][1]
        if a is not None and b is not None and abs(b - a) > jump:
            points[i][1] = None
    return {"expr": str(expr), "label": "y = " + sp.sstr(expr).replace("**", "^"), "points": points,
            "ymin": low - span * 0.1, "ymax": high + span * 0.1}


def calculus(kind: str, text: str, point: str = "0") -> dict:
    expr = parse(text)
    x = SYMBOLS["x"]
    if kind == "derivative":
        result = sp.simplify(sp.diff(expr, x))
        title = "d/dx"
    elif kind == "integral":
        result = sp.integrate(expr, x)
        if result.has(sp.Integral):
            raise ScienceError("whiteboard.error.integral")
        title = "∫ dx"
    elif kind == "limit":
        target = sp.oo if point.strip() in ("oo", "inf", "infinito", "∞") else -sp.oo if point.strip() in ("-oo", "-inf", "-∞") else parse(point)
        result = sp.limit(expr, x, target)
        title = f"lim x→{sp.sstr(target)}"
    else:
        raise ScienceError("whiteboard.error.operation")
    return {"title": title, "input": pretty(expr), "result": pretty(result), "plain": sp.sstr(result).replace("**", "^")}


ATOMIC_MASS = {
    "H": 1.008, "He": 4.0026, "Li": 6.94, "Be": 9.0122, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06, "Cl": 35.45, "Ar": 39.948, "K": 39.098, "Ca": 40.078,
    "Sc": 44.956, "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938, "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38,
    "Ga": 69.723, "Ge": 72.630, "As": 74.922, "Se": 78.971, "Br": 79.904, "Kr": 83.798, "Rb": 85.468, "Sr": 87.62, "Y": 88.906, "Zr": 91.224,
    "Nb": 92.906, "Mo": 95.95, "Tc": 98.0, "Ru": 101.07, "Rh": 102.91, "Pd": 106.42, "Ag": 107.87, "Cd": 112.41, "In": 114.82, "Sn": 118.71,
    "Sb": 121.76, "Te": 127.60, "I": 126.90, "Xe": 131.29, "Cs": 132.91, "Ba": 137.33, "La": 138.91, "Ce": 140.12, "Pr": 140.91, "Nd": 144.24,
    "Pm": 145.0, "Sm": 150.36, "Eu": 151.96, "Gd": 157.25, "Tb": 158.93, "Dy": 162.50, "Ho": 164.93, "Er": 167.26, "Tm": 168.93, "Yb": 173.05,
    "Lu": 174.97, "Hf": 178.49, "Ta": 180.95, "W": 183.84, "Re": 186.21, "Os": 190.23, "Ir": 192.22, "Pt": 195.08, "Au": 196.97, "Hg": 200.59,
    "Tl": 204.38, "Pb": 207.2, "Bi": 208.98, "Po": 209.0, "At": 210.0, "Rn": 222.0, "Fr": 223.0, "Ra": 226.0, "Ac": 227.0, "Th": 232.04,
    "Pa": 231.04, "U": 238.03, "Np": 237.0, "Pu": 244.0, "Am": 243.0, "Cm": 247.0, "Bk": 247.0, "Cf": 251.0, "Es": 252.0, "Fm": 257.0,
    "Md": 258.0, "No": 259.0, "Lr": 266.0, "Rf": 267.0, "Db": 268.0, "Sg": 269.0, "Bh": 270.0, "Hs": 277.0, "Mt": 278.0, "Ds": 281.0,
    "Rg": 282.0, "Cn": 285.0, "Nh": 286.0, "Fl": 289.0, "Mc": 290.0, "Lv": 293.0, "Ts": 294.0, "Og": 294.0,
}
TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)|(\()|(\))(\d*)")


def atoms(formula: str) -> dict[str, int]:
    text = str(formula or "").strip()
    if not text or len(text) > 60:
        raise ScienceError("whiteboard.error.formula")
    total: dict[str, int] = {}
    for part in re.split(r"[·*.]", text):
        lead = re.match(r"^(\d+)", part)
        factor = int(lead.group(1)) if lead else 1
        body = part[lead.end():] if lead else part
        stack = [{}]
        pos = 0
        while pos < len(body):
            m = TOKEN.match(body, pos)
            if not m:
                raise ScienceError("whiteboard.error.formula")
            if m.group(1):
                if m.group(1) not in ATOMIC_MASS:
                    raise ScienceError("whiteboard.error.element")
                stack[-1][m.group(1)] = stack[-1].get(m.group(1), 0) + int(m.group(2) or 1)
            elif m.group(3):
                stack.append({})
            else:
                if len(stack) == 1:
                    raise ScienceError("whiteboard.error.formula")
                group, times = stack.pop(), int(m.group(5) or 1)
                for el, n in group.items():
                    stack[-1][el] = stack[-1].get(el, 0) + n * times
            pos = m.end()
        if len(stack) != 1:
            raise ScienceError("whiteboard.error.formula")
        for el, n in stack[0].items():
            total[el] = total.get(el, 0) + n * factor
    if not total:
        raise ScienceError("whiteboard.error.formula")
    return total


def molar_mass(formula: str) -> dict:
    counts = atoms(formula)
    parts = [{"element": el, "count": n, "mass": round(ATOMIC_MASS[el] * n, 3)} for el, n in counts.items()]
    return {"formula": chem(formula), "parts": parts, "total": round(sum(p["mass"] for p in parts), 3)}


def chem(formula: str) -> str:
    text = re.sub(r"(?<=[A-Za-z)\]])(\d+)", lambda m: m.group(1).translate(SUBSCRIPT), str(formula))
    text = re.sub(r"\^(\d*[+-])", lambda m: m.group(1).translate(SUPERSCRIPT), text)
    return text.replace("->", "→").replace("<=>", "⇌")


def balance(equation: str) -> dict:
    text = str(equation or "").replace("=", "->").replace("→", "->")
    if "->" not in text or len(text) > 160:
        raise ScienceError("whiteboard.error.reaction")
    left, right = text.split("->", 1)
    reactants = [s.strip() for s in left.split("+") if s.strip()]
    products = [s.strip() for s in right.split("+") if s.strip()]
    if not reactants or not products or len(reactants) + len(products) > 10:
        raise ScienceError("whiteboard.error.reaction")
    species = [atoms(s) for s in reactants + products]
    elements = sorted({e for s in species for e in s})
    matrix = sp.Matrix([[s.get(e, 0) * (1 if i < len(reactants) else -1) for i, s in enumerate(species)] for e in elements])
    null = matrix.nullspace()
    if len(null) != 1:
        raise ScienceError("whiteboard.error.unbalanceable")
    vector = null[0]
    lcm = sp.ilcm(*[sp.fraction(v)[1] for v in vector])
    coeffs = [int(v * lcm) for v in vector]
    if any(c == 0 for c in coeffs):
        raise ScienceError("whiteboard.error.unbalanceable")
    if all(c < 0 for c in coeffs):
        coeffs = [-c for c in coeffs]
    if any(c < 0 for c in coeffs):
        raise ScienceError("whiteboard.error.unbalanceable")
    g = math.gcd(*coeffs)
    coeffs = [c // g for c in coeffs]
    show = lambda c, s: f"{'' if c == 1 else c}{chem(s)}"
    left_side = " + ".join(show(c, s) for c, s in zip(coeffs, reactants))
    right_side = " + ".join(show(c, s) for c, s in zip(coeffs[len(reactants):], products))
    return {"coefficients": coeffs, "equation": f"{left_side} → {right_side}", "elements": elements}


UNITS = {
    "m": "meter", "km": "kilometer", "cm": "centimeter", "mm": "millimeter", "s": "second", "min": "minute", "h": "hour",
    "kg": "kilogram", "g": "gram", "N": "newton", "J": "joule", "W": "watt", "Pa": "pascal", "V": "volt", "A": "ampere",
    "ohm": "ohm", "Ω": "ohm", "C": "coulomb", "Hz": "hertz", "K": "kelvin",
}
DERIVED = ("newton", "joule", "watt", "pascal", "volt", "ohm", "coulomb", "hertz", "meter", "second", "kilogram", "ampere")
DERIVED_SYMBOL = {"newton": "N", "joule": "J", "watt": "W", "pascal": "Pa", "volt": "V", "ohm": "Ω", "coulomb": "C", "hertz": "Hz",
                  "meter": "m", "second": "s", "kilogram": "kg", "ampere": "A"}
QUANTITY = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?(?:e-?\d+)?)\s*([A-Za-zΩ/*^·0-9 ]*)\s*$")


def _unit_expr(text: str):
    from sympy.physics import units as u
    raw = text.strip().replace("·", "*").replace("^", "**").replace(" ", "*")
    if not raw:
        return sp.Integer(1)
    if not re.fullmatch(r"[A-Za-zΩ*/0-9()]+", raw):
        raise ScienceError("whiteboard.error.unit")
    names = {k: getattr(u, v) for k, v in UNITS.items()}
    try:
        return parse_expr(raw.replace("Ω", "ohm"), local_dict={**names, "ohm": u.ohm}, evaluate=True)
    except Exception:
        raise ScienceError("whiteboard.error.unit")


def quantity(text: str):
    m = QUANTITY.match(str(text or ""))
    if not m:
        raise ScienceError("whiteboard.error.quantity")
    return sp.Rational(Fraction(m.group(1).replace(",", "."))) * _unit_expr(m.group(2))


def physics(formula: str, known: dict, target: str) -> dict:
    from sympy.physics import units as u
    if "=" not in formula or len(formula) > MAX_EXPR or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,15}", target or ""):
        raise ScienceError("whiteboard.error.formula")
    left, right = formula.split("=", 1)
    calls = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", formula))
    names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", formula)) - calls
    if target not in names or len(names) > 8:
        raise ScienceError("whiteboard.error.formula")
    symbols = {n: sp.Dummy(n) for n in names}
    try:
        lhs = parse_expr(left, local_dict={**FUNCTIONS, **symbols}, transformations=TRANSFORMS)
        rhs = parse_expr(right, local_dict={**FUNCTIONS, **symbols}, transformations=TRANSFORMS)
    except Exception:
        raise ScienceError("whiteboard.error.formula")
    solutions = sp.solve(sp.Eq(lhs, rhs), symbols[target])
    if not solutions:
        raise ScienceError("whiteboard.error.unsolvable")
    solved = solutions[-1]
    values = {symbols[k]: quantity(v) for k, v in known.items() if k in symbols and k != target}
    if set(solved.free_symbols) - set(values):
        raise ScienceError("whiteboard.error.missing")
    result = solved.xreplace(values)
    base = u.convert_to(result, [u.meter, u.second, u.kilogram, u.ampere, u.kelvin])
    shown = None
    for name in DERIVED:
        unit = getattr(u, name)
        converted = sp.simplify(u.convert_to(result, unit) / unit)
        if converted.is_number:
            shown = f"{float(converted):.6g} {DERIVED_SYMBOL[name]}"
            break
    if shown is None:
        coefficient, unit_part = sp.N(base, 6).as_coeff_Mul()
        unit_text = sp.sstr(unit_part).replace("**", "^").replace("*", "·")
        for long, short in (("kilogram", "kg"), ("meter", "m"), ("second", "s"), ("ampere", "A"), ("kelvin", "K")):
            unit_text = unit_text.replace(long, short)
        shown = f"{float(coefficient):.6g} {unit_text}".replace("^2", "²").replace("^3", "³")
    named = solved.xreplace({d: sp.Symbol(n) for n, d in symbols.items()})
    return {"formula": f"{target} = {sp.sstr(named).replace('**', '^')}", "result": f"{target} = {shown}",
            "known": {k: str(v) for k, v in known.items()}}
