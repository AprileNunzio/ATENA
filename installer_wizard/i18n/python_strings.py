import ast
import re

STATUS_KEYWORDS = {"message", "label", "title", "description"}
STATUS_ATTRIBUTES = {"message", "detail", "last_error"}
MODEL_TAG = re.compile(r"\b[\w.-]+:\d+(?:\.\d+)?[bkm]\b", re.I)


def _template(node: ast.AST) -> str | None:
    parts: list[str] = []
    slots = iter(range(100))

    def walk(item: ast.AST) -> bool:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            parts.append(item.value)
        elif isinstance(item, ast.JoinedStr):
            for value in item.values:
                if isinstance(value, ast.Constant):
                    parts.append(str(value.value))
                else:
                    parts.append("{" + str(next(slots)) + "}")
        elif isinstance(item, ast.BinOp) and isinstance(item.op, ast.Add):
            return walk(item.left) and walk(item.right)
        elif isinstance(item, (ast.Name, ast.Attribute, ast.Call, ast.Subscript)):
            parts.append("{" + str(next(slots)) + "}")
        else:
            return False
        return True

    if not walk(node):
        return None
    text = re.sub(r"\s+", " ", "".join(parts)).strip()
    if MODEL_TAG.search(text) or not re.search(r"[A-Za-zÀ-ÿ]{3,}", re.sub(r"\{\d+\}", "", text)):
        return None
    return text


def _step_strings(call: ast.Call) -> list[ast.AST]:
    return [arg for arg in call.args[2:4]]


def _phase_strings(call: ast.Call) -> list[ast.AST]:
    return call.args[1:2]


def status_strings(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        candidates: list[ast.AST] = []
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name == "Step":
                candidates += _step_strings(node)
            elif name == "set_phase":
                candidates += _phase_strings(node)
            candidates += [k.value for k in node.keywords if k.arg in STATUS_KEYWORDS]
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Attribute) and t.attr in STATUS_ATTRIBUTES for t in node.targets):
                candidates.append(node.value)
        for candidate in candidates:
            text = _template(candidate)
            if text and text not in found:
                found.append(text)
    return found
