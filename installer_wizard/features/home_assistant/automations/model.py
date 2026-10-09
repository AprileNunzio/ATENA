import json
import re
import time

MODES = ("single", "restart", "queued", "parallel")
SECTIONS = (("trigger", "triggers"), ("condition", "conditions"), ("action", "actions"))
MAX_BYTES = 64 * 1024
MAX_DEPTH = 14
MAX_STRING = 4000
_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_ENTITY = re.compile(r"^automation\.[a-z0-9_]{1,120}$")
_KEY = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class AutomationError(ValueError):
    pass


def new_id() -> str:
    return str(int(time.time() * 1000))


def check_id(value: str) -> str:
    if not _ID.match(str(value or "")):
        raise AutomationError("Identificativo dell'automazione non valido")
    return str(value)


def check_entity(value: str) -> str:
    if not _ENTITY.match(str(value or "")):
        raise AutomationError("Entità dell'automazione non valida")
    return str(value)


def _walk(node, depth: int = 0):
    if depth > MAX_DEPTH:
        raise AutomationError("Automazione troppo annidata")
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str) or not _KEY.match(key):
                raise AutomationError(f"Chiave non ammessa: {str(key)[:40]}")
            _walk(value, depth + 1)
    elif isinstance(node, list):
        for item in node:
            _walk(item, depth + 1)
    elif isinstance(node, str):
        if len(node) > MAX_STRING:
            raise AutomationError("Testo troppo lungo nell'automazione")
    elif node is not None and not isinstance(node, (int, float, bool)):
        raise AutomationError("Valore non ammesso nell'automazione")


def _items(raw: dict, singular: str, plural: str) -> list:
    value = raw.get(plural, raw.get(singular))
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    for item in items:
        if not isinstance(item, (dict, str)):
            raise AutomationError(f"Elemento non valido in «{plural}»")
    return items


def normalize(raw) -> dict:
    if not isinstance(raw, dict):
        raise AutomationError("L'automazione deve essere un oggetto")
    alias = str(raw.get("alias") or "").strip()[:200]
    if not alias:
        raise AutomationError("Dai un nome all'automazione")
    mode = str(raw.get("mode") or "single")
    if mode not in MODES:
        raise AutomationError("Modalità di esecuzione non valida")
    out = {"alias": alias, "description": str(raw.get("description") or "")[:2000], "mode": mode}
    if mode in ("queued", "parallel") and raw.get("max") is not None:
        try:
            out["max"] = max(1, min(int(raw["max"]), 100))
        except (TypeError, ValueError) as exc:
            raise AutomationError("Numero massimo di esecuzioni non valido") from exc
    for singular, plural in SECTIONS:
        out[plural] = _items(raw, singular, plural)
    if not out["triggers"]:
        raise AutomationError("Serve almeno un innesco («quando»)")
    if not out["actions"]:
        raise AutomationError("Serve almeno un'azione («allora»)")
    for extra in ("variables", "trigger_variables"):
        if isinstance(raw.get(extra), dict):
            out[extra] = raw[extra]
    _walk(out)
    if len(json.dumps(out, ensure_ascii=False).encode()) > MAX_BYTES:
        raise AutomationError("Automazione troppo grande")
    return out


def entity_ids(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "entity_id":
                found.update(v for v in (value if isinstance(value, list) else [value]) if isinstance(v, str))
            else:
                found |= entity_ids(value)
    elif isinstance(node, list):
        for item in node:
            found |= entity_ids(item)
    return found
