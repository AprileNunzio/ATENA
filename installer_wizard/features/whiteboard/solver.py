import ast
import re
from fractions import Fraction

MAX_LENGTH = 120
MAX_EXPONENT = 12
MAX_DIGITS = 40
WORDS = (("elevato alla", "**"), ("elevato a", "**"), ("alla", "**"), ("diviso per", "/"), ("diviso", "/"), ("fratto", "/"), ("moltiplicato per", "*"),
         ("per", "*"), ("volte", "*"), ("più", "+"), ("piu", "+"), ("meno", "-"))
SYMBOLS = (("×", "*"), ("÷", "/"), (":", "/"), ("−", "-"), ("^", "**"), (",", "."))
PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "**": 3}
SHOW = {"+": "+", "-": "−", "*": "×", "/": "÷", "**": "^"}


def normalize(text: str, equation: bool) -> str:
    t = " " + str(text).lower() + " "
    for word, symbol in WORDS:
        t = re.sub(rf"(?<=[\d)a-z]) {word} (?=[\d(a-z])", f" {symbol} ", t)
    for old, new in SYMBOLS:
        t = t.replace(old, new)
    if not equation:
        t = re.sub(r"(?<=[\d)])\s*x\s*(?=[\d(])", "*", t)
    t = re.sub(r"(?<=\d)\s*(?=[a-z(])", "*", t) if equation else t
    t = re.sub(r"(?<=[a-z)])\s*(?=\d|\()", "*", t) if equation else t
    return re.sub(r"\s+", "", t)


def num(value) -> tuple:
    return ("num", Fraction(value))


def build(node, allowed: set[str]) -> tuple:
    if isinstance(node, ast.Expression):
        return build(node.body, allowed)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return num(str(node.value))
    if isinstance(node, ast.Name) and node.id in allowed:
        return ("var", node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = build(node.operand, allowed)
        return ("neg", inner) if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.BinOp):
        op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "**"}.get(type(node.op))
        if op:
            return ("bin", op, build(node.left, allowed), build(node.right, allowed))
    raise ValueError("espressione non valida")


def parse(text: str, allowed: set[str] | None = None) -> tuple:
    if len(text) > MAX_LENGTH or not text:
        raise ValueError("espressione vuota o troppo lunga")
    try:
        return build(ast.parse(text, mode="eval"), allowed or set())
    except SyntaxError:
        raise ValueError("espressione non valida")


def fmt(value: Fraction) -> str:
    sign = "−" if value < 0 else ""
    value = abs(value)
    if value.denominator == 1:
        return f"{sign}{value.numerator}"
    rest, power = value.denominator, 0
    for prime in (2, 5):
        while rest % prime == 0:
            rest //= prime
            power += 1
    if rest == 1:
        return f"{sign}{float(value):.{power}f}".replace(".", ",")
    return f"{sign}{value.numerator}/{value.denominator} ≈ {sign}{float(value):.4f}".replace(".", ",")

def render(node: tuple, parent: int = 0, right: bool = False) -> str:
    kind = node[0]
    if kind == "num":
        text = fmt(node[1])
        return f"({text})" if node[1] < 0 and parent else text
    if kind == "var":
        return node[1]
    if kind == "neg":
        return f"−{render(node[1], 4)}" if not parent else f"(−{render(node[1], 4)})"
    if node[1] == "*" and node[2][0] == "num" and node[3][0] == "var":
        return f"{fmt(node[2][1])}{node[3][1]}"
    prec = PREC[node[1]]
    text =f"{render(node[2], prec)} {SHOW[node[1]]} {render(node[3], prec, True)}"
    return f"({text})" if prec < parent or (right and prec == parent and node[1] in "-/") else text


def apply(op: str, a: Fraction, b: Fraction) -> Fraction:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise ValueError("divisione per zero")
        return a / b
    if b.denominator != 1 or abs(b) > MAX_EXPONENT:
        raise ValueError("esponente troppo grande o non intero")
    if a == 0 and b < 0:
        raise ValueError("divisione per zero")
    result = a ** int(b)
    if len(str(abs(result.numerator))) > MAX_DIGITS:
        raise ValueError("risultato troppo grande")
    return result


def reduce_once(node: tuple) -> tuple:
    kind = node[0]
    if kind == "neg":
        return num(-node[1][1]) if node[1][0] == "num" else ("neg", reduce_once(node[1]))
    if kind == "bin":
        left, right = node[2], node[3]
        if left[0] == "num" and right[0] == "num":
            return num(apply(node[1], left[1], right[1]))
        if left[0] != "num":
            return ("bin", node[1], reduce_once(left), right)
        return ("bin", node[1], left, reduce_once(right))
    return node


def arithmetic(text: str) -> dict:
    tree = parse(normalize(text, False))
    lines = [render(tree)]
    for _ in range(60):
        if tree[0] == "num":
            break
        tree = reduce_once(tree)
        line = render(tree)
        if line != lines[-1]:
            lines.append(line)
    result = lines[-1]
    return {"kind": "expression", "lines": [lines[0]] + [f"= {line}" for line in lines[1:]], "result": result,
            "speech": f"{lines[0]} fa {result}."}


def linear(node: tuple, var: str) -> tuple[Fraction, Fraction]:
    kind = node[0]
    if kind == "num":
        return Fraction(0), node[1]
    if kind == "var":
        if node[1] != var:
            raise ValueError("una sola incognita per volta")
        return Fraction(1), Fraction(0)
    if kind == "neg":
        a, b = linear(node[1], var)
        return -a, -b
    op = node[1]
    (a1, b1), (a2, b2) = linear(node[2], var), linear(node[3], var)
    if op in "+-":
        sign = 1 if op == "+" else -1
        return a1 + sign * a2, b1 + sign * b2
    if op == "*":
        if a1 and a2:
            raise ValueError("l'equazione non è di primo grado")
        return (a1 * b2 + a2 * b1, b1 * b2)
    if op == "/":
        if a2 or b2 == 0:
            raise ValueError("divisione non valida")
        return a1 / b2, b1 / b2
    if a1 or a2:
        raise ValueError("l'equazione non è di primo grado")
    return Fraction(0), apply("**", b1, b2)


def term(a: Fraction, var: str) -> str:
    if a == 1:
        return var
    if a == -1:
        return f"−{var}"
    return f"{fmt(a)}{var}"


def side(a: Fraction, b: Fraction, var: str) -> str:
    if a == 0:
        return fmt(b)
    if b == 0:
        return term(a, var)
    return f"{term(a, var)} {'+' if b > 0 else '−'} {fmt(abs(b))}"


def equation(text: str) -> dict:
    cleaned = normalize(text, True)
    if cleaned.count("=") != 1:
        raise ValueError("serve un solo uguale")
    letters = set(re.findall(r"[a-z]", cleaned))
    if len(letters) != 1:
        raise ValueError("serve una sola incognita")
    var = letters.pop()
    left, right = (parse(s, {var}) for s in cleaned.split("="))
    (a1, b1), (a2, b2) = linear(left, var), linear(right, var)
    lines = [f"{render(left)} = {render(right)}"]
    shifted = a1 - a2
    constant = b2 - b1
    if side(a1, b1, var) + " = " + side(a2, b2, var) != lines[0]:
        lines.append(f"{side(a1, b1, var)} = {side(a2, b2, var)}")
    if shifted == 0:
        verdict = "vera per ogni valore: infinite soluzioni" if constant == 0 else "non ha soluzioni"
        return {"kind": "equation", "lines": lines + [verdict], "result": verdict, "speech": f"L'equazione {verdict}."}
    if a2 != 0 or b1 != 0:
        left_text = term(shifted, var) if a2 == 0 else f"{term(a1, var)} − {term(a2, var) if a2 > 0 else '(' + term(a2, var) + ')'}"
        right_text = fmt(b2) if b1 == 0 else f"{fmt(b2)} {'−' if b1 > 0 else '+'} {fmt(abs(b1))}"
        lines.append(f"{left_text} = {right_text}")
        lines.append(f"{term(shifted, var)} = {fmt(constant)}")
    value = constant / shifted
    if shifted != 1:
        lines.append(f"{var} = {fmt(constant)} ÷ {fmt(shifted) if shifted > 0 else '(' + fmt(shifted) + ')'}")
    lines.append(f"{var} = {fmt(value)}")
    return {"kind": "equation", "lines": lines, "result": f"{var} = {fmt(value)}", "speech": f"{var} vale {fmt(value)}."}


def solve(text: str) -> dict:
    return equation(text) if "=" in text else arithmetic(text)
