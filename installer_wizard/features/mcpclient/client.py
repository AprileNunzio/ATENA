import json

import httpx

PROTOCOL = "2025-06-18"
TIMEOUT = 30.0
MAX_PAGES = 5


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)


def headers(server: dict, session: str = "") -> dict:
    out = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTOCOL}
    if server.get("token"):
        out["Authorization"] = f"Bearer {server['token']}"
    if session:
        out["Mcp-Session-Id"] = session
    return out


def decode(response: httpx.Response, ident: int):
    if "text/event-stream" in response.headers.get("content-type", ""):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    message = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(message, dict) and message.get("id") == ident:
                    return message
        raise RuntimeError("risposta del server senza esito")
    return response.json()


class Link:

    def __init__(self, client: httpx.AsyncClient, server: dict) -> None:
        self.client, self.server, self.session, self.counter = client, server, "", 0

    async def post(self, body: dict) -> httpx.Response:
        response = await self.client.post(self.server["url"], json=body, headers=headers(self.server, self.session))
        if response.status_code in (401, 403):
            raise RuntimeError("accesso negato dal server: controlla il token")
        if response.status_code >= 400:
            raise RuntimeError(f"il server ha risposto {response.status_code}")
        return response

    async def rpc(self, method: str, params: dict | None = None):
        self.counter += 1
        response = await self.post({"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params or {}})
        message = decode(response, self.counter)
        if "error" in message:
            raise RuntimeError(str(message["error"].get("message", "errore del server"))[:200])
        return message.get("result") or {}

    async def open(self) -> dict:
        self.counter += 1
        response = await self.post({"jsonrpc": "2.0", "id": self.counter, "method": "initialize",
                                    "params": {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "atena-os", "version": "4.1.47"}}})
        self.session = response.headers.get("mcp-session-id", "")
        info = decode(response, self.counter)
        if "error" in info:
            raise RuntimeError(str(info["error"].get("message", "errore del server"))[:200])
        await self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return info.get("result") or {}


async def list_tools(server: dict) -> list[dict]:
    async with new_client() as client:
        link = Link(client, server)
        await link.open()
        tools, cursor = [], None
        for _ in range(MAX_PAGES):
            page = await link.rpc("tools/list", {"cursor": cursor} if cursor else {})
            tools += [t for t in page.get("tools", []) if isinstance(t, dict) and t.get("name")]
            cursor = page.get("nextCursor")
            if not cursor:
                break
        return tools


async def call_tool(server: dict, name: str, arguments: dict) -> str:
    async with new_client() as client:
        link = Link(client, server)
        await link.open()
        result = await link.rpc("tools/call", {"name": name, "arguments": arguments})
    text = "\n".join(str(p.get("text", "")) for p in result.get("content", []) if isinstance(p, dict) and p.get("type") == "text").strip()
    if result.get("isError"):
        raise RuntimeError(text[:300] or "il server ha segnalato un errore")
    return text or "fatto"
