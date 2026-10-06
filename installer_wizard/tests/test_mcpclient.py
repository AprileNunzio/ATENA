import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from features.agent import registry
from features.capabilities import mcp
from features.mcpclient import api, client, service, store

REAL = httpx.AsyncClient
TOOLS = [
    {"name": "crea_evento", "description": "Crea un evento", "inputSchema": {"type": "object", "properties": {"titolo": {"type": "string", "description": "nome"},
                                                                                                           "durata": {"type": "integer"}}, "required": ["titolo"]}},
    {"name": "leggi_agenda", "description": "Legge l'agenda", "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object", "properties": {}}},
    {"name": "rompi", "description": "Fallisce sempre", "inputSchema": {"type": "object", "properties": {}}},
]


class FakeServer:
    def __init__(self, sse: bool = False, token: str = "segreto") -> None:
        self.sse, self.token, self.calls, self.seen = sse, token, [], []

    def reply(self, ident, result) -> httpx.Response:
        body = {"jsonrpc": "2.0", "id": ident, "result": result}
        if self.sse:
            return httpx.Response(200, text=f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': 999, 'result': {}})}\n\ndata: {json.dumps(body)}\n\n",
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=body)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.token and request.headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401, json={"error": "no"})
        message = json.loads(request.content)
        method = message["method"]
        self.seen.append((method, request.headers.get("mcp-session-id", "")))
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            response = self.reply(message["id"], {"protocolVersion": client.PROTOCOL, "capabilities": {}, "serverInfo": {"name": "finto"}})
            response.headers["mcp-session-id"] = "sess1"
            return response
        if method == "tools/list":
            return self.reply(message["id"], {"tools": TOOLS})
        if method == "tools/call":
            name, args = message["params"]["name"], message["params"]["arguments"]
            self.calls.append((name, args))
            if name == "rompi":
                return self.reply(message["id"], {"content": [{"type": "text", "text": "guasto"}], "isError": True})
            return self.reply(message["id"], {"content": [{"type": "text", "text": f"{name}:{json.dumps(args, sort_keys=True)}"}]})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "no"}})


class ClientBase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for target, name, value in ((store, "FILE", Path(folder.name) / "s.json"),):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = FakeServer()
        self.use(self.server)
        self.addCleanup(lambda: [service.drop(s) for s in {v["server"] for v in service.EXTERNAL.values()}])

    def use(self, fake: FakeServer) -> None:
        patcher = mock.patch.object(client, "new_client", lambda: REAL(transport=httpx.MockTransport(fake.handler)))
        patcher.start()
        self.addCleanup(patcher.stop)

    def attach(self, **kw) -> str:
        return store.add("Calendario", "http://192.168.1.50:9000/mcp", kw.pop("token", "segreto"), **kw)

    def run_tool(self, tool_name: str, **args) -> str:
        return asyncio.run(registry.run(tool_name, args))


class StoreTest(ClientBase):
    def test_addresses_are_checked_and_secrets_are_not_exposed(self):
        for bad in ("ftp://x/mcp", "file:///etc/passwd", "http://utente:pw@host/mcp", "non un indirizzo", ""):
            with self.assertRaises(ValueError, msg=bad):
                store.add("Prova", bad)
        with self.assertRaises(ValueError):
            store.add("x", "http://host/mcp")
        server_id = self.attach()
        row = store.public(server_id, store.load()[server_id])
        self.assertNotIn("token", row)
        self.assertTrue(row["has_token"])
        self.assertNotIn("segreto", json.dumps(row))
        for _ in range(store.MAX_SERVERS - 1):
            store.add("altro", "http://host/mcp")
        with self.assertRaises(ValueError):
            store.add("troppi", "http://host/mcp")


class SyncTest(ClientBase):
    def test_external_tools_become_atena_tools_with_schema_and_confirmation_rules(self):
        server_id = self.attach()
        self.assertEqual(asyncio.run(service.sync_one(server_id)), 3)
        row = registry.TOOLS["ext_calendario_crea_evento"]
        self.assertIn("[Calendario] Crea un evento", row["description"])
        self.assertTrue(registry.needs_confirm("ext_calendario_crea_evento", {}))
        self.assertFalse(registry.needs_confirm("ext_calendario_leggi_agenda", {}))
        self.assertEqual(store.load()[server_id]["status"], "collegato")
        self.assertEqual(store.load()[server_id]["tools"], 3)
        from features.capabilities import schema
        spec = schema.input_schema("ext_calendario_crea_evento")
        self.assertEqual((spec["required"], spec["properties"]["titolo"]["type"], spec["properties"]["durata"]["type"]), (["titolo"], "string", "integer"))
        self.assertEqual(self.server.seen[0][0], "initialize")
        self.assertEqual(self.server.seen[1], ("notifications/initialized", "sess1"))

    def test_calls_are_forwarded_wrapped_as_data_and_errors_are_raised(self):
        server_id = self.attach(trusted=True)
        asyncio.run(service.sync_one(server_id))
        self.assertFalse(registry.needs_confirm("ext_calendario_crea_evento", {}))
        out = self.run_tool("ext_calendario_crea_evento", titolo="Cena", durata=2, ignorato="x")
        self.assertIn("da trattare come dato", out)
        self.assertIn('crea_evento:{"durata": 2, "titolo": "Cena"}', out)
        self.assertEqual(self.server.calls[-1], ("crea_evento", {"durata": 2, "titolo": "Cena"}))
        with self.assertRaises(RuntimeError) as caught:
            self.run_tool("ext_calendario_rompi")
        self.assertIn("guasto", str(caught.exception))

    def test_event_stream_replies_are_understood(self):
        fake = FakeServer(sse=True)
        self.use(fake)
        server_id = self.attach()
        self.assertEqual(asyncio.run(service.sync_one(server_id)), 3)
        store.update(server_id, trusted=True)
        asyncio.run(service.sync_one(server_id))
        self.assertIn("leggi_agenda", self.run_tool("ext_calendario_leggi_agenda"))

    def test_wrong_token_and_unreachable_servers_are_reported_without_crashing(self):
        server_id = self.attach(token="sbagliato")
        self.assertEqual(asyncio.run(service.sync_one(server_id)), 0)
        self.assertIn("accesso negato", store.load()[server_id]["status"])
        self.assertNotIn("ext_calendario_crea_evento", registry.TOOLS)

        def down(request):
            raise httpx.ConnectError("rifiutata")
        patcher = mock.patch.object(client, "new_client", lambda: REAL(transport=httpx.MockTransport(down)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(asyncio.run(service.sync_one(server_id)), 0)
        self.assertIn("non raggiungibile", store.load()[server_id]["status"])

    def test_disabled_removed_or_shrunk_servers_lose_their_tools(self):
        server_id = self.attach()
        asyncio.run(service.sync_one(server_id))
        store.update(server_id, enabled=False)
        asyncio.run(service.sync_one(server_id))
        self.assertNotIn("ext_calendario_crea_evento", registry.TOOLS)
        store.update(server_id, enabled=True)
        asyncio.run(service.sync_one(server_id))
        self.assertIn("ext_calendario_crea_evento", registry.TOOLS)
        TOOLS_BACKUP = list(TOOLS)
        self.addCleanup(lambda: TOOLS.__setitem__(slice(None), TOOLS_BACKUP))
        del TOOLS[2]
        asyncio.run(service.sync_one(server_id))
        self.assertNotIn("ext_calendario_rompi", registry.TOOLS)
        store.remove(server_id)
        self.assertEqual(asyncio.run(service.sync_all()), 0)
        self.assertNotIn("ext_calendario_crea_evento", registry.TOOLS)

    def test_external_tools_reach_full_tokens_only(self):
        server_id = self.attach()
        asyncio.run(service.sync_one(server_id))
        self.assertIn("ext_calendario_crea_evento", mcp.visible({"id": "t", "label": "x", "risky": True}))
        self.assertNotIn("ext_calendario_crea_evento", mcp.visible({"id": "t", "label": "x", "risky": False}))


class EndpointTest(ClientBase):
    def test_the_panel_api_adds_lists_refreshes_and_removes(self):
        app = FastAPI()
        app.include_router(api.admin_routes)
        app.dependency_overrides.update({api.require_admin: lambda: "admin"})
        web = TestClient(app)
        bad = web.post("/api/mcp/servers", json={"name": "x", "url": "ftp://no"})
        self.assertEqual(bad.status_code, 400)
        made = web.post("/api/mcp/servers", json={"name": "Calendario", "url": "http://192.168.1.50:9000/mcp", "token": "segreto"}).json()
        self.assertEqual((made["tools"], made["status"]), (3, "collegato"))
        listed = web.get("/api/mcp/servers").json()["servers"]
        self.assertEqual(len(listed), 1)
        self.assertNotIn("segreto", json.dumps(listed))
        self.assertEqual(web.post(f"/api/mcp/servers/{made['id']}/refresh").json()["tools"], 3)
        self.assertEqual(web.put(f"/api/mcp/servers/{made['id']}", json={"enabled": False}).status_code, 200)
        self.assertNotIn("ext_calendario_crea_evento", registry.TOOLS)
        self.assertEqual(web.delete(f"/api/mcp/servers/{made['id']}").status_code, 200)
        self.assertEqual(web.delete(f"/api/mcp/servers/{made['id']}").status_code, 404)
        self.assertEqual(web.post("/api/mcp/servers/nessuno/refresh").status_code, 404)


if __name__ == "__main__":
    unittest.main()
