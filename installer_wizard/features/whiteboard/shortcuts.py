import ast

SMALL = 10


def _numbers(node: ast.AST) -> list[int] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return [node.value]
    if isinstance(node, ast.BinOp):
        left, right = _numbers(node.left), _numbers(node.right)
        return None if left is None or right is None else left + right
    return None


def _ops(node: ast.AST) -> list[type]:
    if isinstance(node, ast.BinOp):
        return _ops(node.left) + [type(node.op)] + _ops(node.right)
    return []


def _pair(a: int, b: int, op: type) -> str:
    small, big = sorted((a, b))
    if op is ast.Mult:
        if small == 5:
            return f"×5 è come ×10 e poi metà: {big}×10 = {big * 10}, metà = {big * 5}."
        if small == 25:
            return f"×25 è come ×100 e poi diviso 4: {big}×100 = {big * 100}, ÷4 = {big * 25}."
        if small in (9, 99):
            return f"×{small} è come ×{small + 1} meno una volta: {big * (small + 1)} − {big} = {big * small}."
        if small == 11 and 10 <= big <= 99:
            tens, units = divmod(big, 10)
            carry = " (se supera 9 riporta 1 sulla prima cifra)" if tens + units > 9 else ""
            return f"×11 con due cifre: somma le cifre ({tens}+{units}) e mettila in mezzo{carry} → {big * 11}."
        if a == b and a % 10 == 5:
            n = a // 10
            return f"Quadrato di un numero che finisce per 5: {n}×{n + 1} = {n * (n + 1)}, poi scrivi 25 in fondo → {a * a}."
        mid = (a + b) // 2
        if (a + b) % 2 == 0 and a != b and mid % 10 == 0:
            d = abs(a - mid)
            return f"Numeri vicini a {mid}: {mid}² − {d}² = {mid * mid} − {d * d} = {a * b}."
        if big >= SMALL and small < SMALL:
            tens = big - big % 10
            return f"Spezza il numero: {tens}×{small} + {big % 10}×{small} = {tens * small} + {big % 10 * small} = {a * b}."
    if op is ast.Add:
        near = next((n for n in (big, small) if n >= SMALL and n % 10 in (8, 9)), None)
        if near is not None:
            other, up = a + b - near, 10 - near % 10
            return f"Arrotonda {near} a {near + up}: {other} + {near + up} = {other + near + up}, poi togli {up} → {a + b}."
    if op is ast.Sub and b >= SMALL and b % 10 in (8, 9):
        up = 10 - b % 10
        return f"Arrotonda {b} a {b + up}: {a} − {b + up} = {a - b - up}, poi aggiungi {up} → {a - b}."
    if op is ast.Div and b == 5 and a % 5 == 0:
        return f"÷5 è come ×2 e poi ÷10: {a}×2 = {a * 2}, ÷10 = {a // 5}."
    return ""


def arithmetic(expression: str) -> str:
    try:
        tree = ast.parse(expression.replace("×", "*").replace("÷", "/").replace(":", "/"), mode="eval").body
    except SyntaxError:
        return ""
    numbers, ops = _numbers(tree), _ops(tree)
    if not numbers or not ops or all(n < SMALL for n in numbers):
        return ""
    if len(ops) == 1:
        return _pair(numbers[0], numbers[1], ops[0])
    if all(op is ast.Add for op in ops) and len(numbers) >= 3:
        return "Con tante somme, raggruppa prima i numeri che insieme fanno 10 o 100, poi aggiungi il resto."
    if any(op in (ast.Mult, ast.Div) for op in ops) and any(op in (ast.Add, ast.Sub) for op in ops):
        return "Prima moltiplicazioni e divisioni, poi somme e sottrazioni: segna sotto ogni prodotto il suo risultato."
    return ""


SYMBOLIC = {
    "derivative": "Per ogni termine a·xⁿ porta giù l'esponente e abbassalo di 1 (a·n·xⁿ⁻¹); le costanti spariscono.",
    "integral": "Per ogni termine a·xⁿ alza l'esponente di 1 e dividi per il nuovo esponente; non dimenticare + c.",
    "limit": "Riconosci i limiti notevoli (sin x / x → 1, (1+1/n)ⁿ → e): li scrivi subito senza calcoli.",
    "equation": "Porta le x a sinistra e i numeri a destra cambiando segno, poi dividi per il coefficiente della x.",
}


def symbolic(kind: str) -> str:
    return SYMBOLIC.get(kind, "")
