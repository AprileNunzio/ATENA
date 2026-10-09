import time

from features.agent import registry
from features.agent.paths import level
from features.authz.principal import Principal, Strength, act_as, current
from features.capabilities import audit, catalog, schema
from features.team import roster, runner

SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")
INFO = {"name": "atena-os", "version": "4.1.39"}
SAFE_AGENTS = {"music", "cameras", "desktop", "agent", "whiteboard"}
INSTRUCTIONS = ("Atena OS: ogni strumento appartiene a un agente con una priorità. Leggi il prompt «panoramica» e le risorse atena://capabilities e "
                "atena://team per sapere cosa fa la squadra. Le azioni delicate richiedono _confirm=true dopo la conferma dell'utente.")


class RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def agents_of(token: dict) -> set[str] | None:
    return None if token["risky"] else SAFE_AGENTS


def visible(token: dict) -> list[str]:
    if token["risky"]:
        return [t["name"] for t in registry.available(level())]
    return [t["name"] for t in registry.available(level()) if not t["confirm"] and roster.owner(t["name"]) in SAFE_AGENTS]


def listing(token: dict) -> dict:
    return {"tools": [{**schema.definition(n), "annotations": catalog.annotations(n)} for n in visible(token)]}


def text(value: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": value}], "isError": error}


async def call(params: dict, token: dict) -> dict:
    name = str(params.get("name", ""))
    args = dict(params.get("arguments") or {})
    if name not in visible(token):
        raise RpcError(-32602, f"strumento «{name}» sconosciuto o non consentito a questo token")
    confirmed = args.pop("_confirm", False) is True
    missing = [k for k in schema.input_schema(name)["required"] if k not in args]
    if missing:
        return text(f"mancano gli argomenti: {', '.join(missing)}", True)
    if registry.needs_confirm(name, args):
        if not token["risky"]:
            return text("azione che richiede la conferma dell'utente: questo token non può eseguirla", True)
        if not confirmed:
            return text("azione delicata: chiedi conferma all'utente e richiama con _confirm=true", True)
    started = time.time()
    principal = Principal(slug=f"mcp:{token.get('name') or token.get('id') or 'token'}", role="system",
                          strength=Strength.STRONG, factors=("token",))
    acting = act_as(principal)
    try:
        reply = text(await runner.run_as(name, args))
    except Exception as exc:
        reply = text(f"errore: {str(exc)[:300]}", True)
    finally:
        current.reset(acting)
    audit.record(token, "tools/call", name, not reply["isError"], (time.time() - started) * 1000)
    return reply


def read(params: dict, token: dict) -> dict:
    uri = str(params.get("uri", ""))
    allowed = agents_of(token)
    try:
        if uri.startswith(catalog.AGENT_URI) and allowed is not None and roster.find(uri[len(catalog.AGENT_URI):]) not in allowed:
            raise KeyError(uri)
        mime, body = catalog.read(uri)
    except KeyError:
        raise RpcError(-32002, "risorsa sconosciuta o non consentita")
    return {"contents": [{"uri": uri, "mimeType": mime, "text": body}]}


def prompt(params: dict) -> dict:
    try:
        return catalog.prompt(str(params.get("name", "")), params.get("arguments") or {})
    except KeyError:
        raise RpcError(-32602, "prompt o agente sconosciuto")


async def dispatch(method: str, params: dict, token: dict) -> dict:
    if method == "initialize":
        asked = str(params.get("protocolVersion", ""))
        return {"protocolVersion": asked if asked in SUPPORTED else SUPPORTED[0], "serverInfo": INFO, "instructions": INSTRUCTIONS,
                "capabilities": {"tools": {"listChanged": True}, "resources": {}, "prompts": {}}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return listing(token)
    if method == "tools/call":
        return await call(params, token)
    if method == "resources/list":
        return {"resources": catalog.resources(agents_of(token))}
    if method == "resources/templates/list":
        return {"resourceTemplates": catalog.templates()}
    if method == "resources/read":
        return read(params, token)
    if method == "prompts/list":
        return {"prompts": catalog.prompts()}
    if method == "prompts/get":
        return prompt(params)
    raise RpcError(-32601, f"metodo «{method}» non supportato")


async def handle(message, token: dict) -> dict | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "richiesta non valida"}}
    ident = message.get("id")
    if ident is None:
        return None
    params = message.get("params")
    if not audit.allow(token["id"]):
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32000, "message": "troppe richieste: riprova tra un minuto"}}
    try:
        result = await dispatch(message["method"], params if isinstance(params, dict) else {}, token)
    except RpcError as exc:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": exc.code, "message": exc.message}}
    return {"jsonrpc": "2.0", "id": ident, "result": result}
