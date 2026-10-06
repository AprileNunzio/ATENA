import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from features.capabilities import api, audit, mcp, schema, tokens


def rpc(method: str, params: dict | None = None, ident: int | None = 1) -> dict:
    message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if ident is not None:
        message["id"] = ident
    return message


class SchemaTest(unittest.TestCase):
    def test_signatures_become_json_schema(self):
        play = schema.input_schema("music_play")
        self.assertEqual(play["required"], [])
        self.assertEqual(play["properties"]["query"]["type"], "string")
        control = schema.input_schema("music_control")
        self.assertEqual(control["required"], ["action"])
        self.assertEqual(control["properties"]["value"]["type"], "number")
        self.assertEqual(schema.input_schema("show_widget")["properties"]["data"]["type"], "object")
        self.assertEqual(schema.openai("music_now")["function"]["name"], "music_now")
        self.assertIn("input_schema", schema.anthropic("music_now"))


class TokenBase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(tokens, "FILE", Path(folder.name) / "t.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        tokens.FAILS.clear()
        self.safe = tokens.create("lettura")
        self.risky = tokens.create("completo", True)

    def who(self, created: dict) -> dict:
        return tokens.check("Bearer " + created["token"], "10.0.0.1")


class TokenTest(TokenBase):
    def test_tokens_are_checked_stored_hashed_revoked_and_rate_limited(self):
        self.assertEqual(self.who(self.safe)["label"], "lettura")
        self.assertTrue(self.who(self.risky)["risky"])
        self.assertNotIn(self.safe["token"], tokens.FILE.read_text())
        self.assertIsNone(tokens.check("Bearer sbagliato", "10.0.0.1"))
        self.assertIsNone(tokens.check("", "10.0.0.1"))
        self.assertTrue(tokens.revoke(self.safe["id"]))
        self.assertIsNone(self.who(self.safe))
        self.assertFalse(tokens.revoke("nessuno"))
        for _ in range(8):
            tokens.check("Bearer x", "10.9.9.9")
        self.assertIsNone(tokens.check("Bearer " + self.risky["token"], "10.9.9.9"))


class ProtocolTest(TokenBase):
    def ask(self, created: dict, method: str, params: dict | None = None):
        return asyncio.run(mcp.handle(rpc(method, params), self.who(created)))

    def test_handshake_listing_and_resources(self):
        init = self.ask(self.safe, "initialize")["result"]
        self.assertEqual(init["protocolVersion"], mcp.SUPPORTED[0])
        self.assertEqual(self.ask(self.safe, "initialize", {"protocolVersion": "2024-11-05"})["result"]["protocolVersion"], "2024-11-05")
        self.assertTrue(init["capabilities"]["tools"]["listChanged"])
        self.assertIsNone(asyncio.run(mcp.handle(rpc("notifications/initialized", ident=None), self.who(self.safe))))
        names = {t["name"] for t in self.ask(self.safe, "tools/list")["result"]["tools"]}
        self.assertTrue({"music_play", "open_camera", "agent_info"} <= names)
        for forbidden in ("run_command", "agent_set", "read_file", "write_file", "http_get", "schedule_task", "agent_ask"):
            self.assertNotIn(forbidden, names)
        full = {t["name"] for t in self.ask(self.risky, "tools/list")["result"]["tools"]}
        self.assertTrue({"run_command", "agent_set"} <= full)
        uris = [r["uri"] for r in self.ask(self.safe, "resources/list")["result"]["resources"]]
        self.assertTrue({"atena://capabilities", "atena://team", "atena://widgets", "atena://agent/music"} <= set(uris))
        self.assertNotIn("atena://agent/vault", uris)
        self.assertIn("error", self.ask(self.safe, "resources/read", {"uri": "atena://agent/vault"}))
        self.assertIn("music_play", self.ask(self.safe, "resources/read", {"uri": "atena://agent/music"})["result"]["contents"][0]["text"])
        self.assertIn("atena://agent/{id}", str(self.ask(self.safe, "resources/templates/list")))
        text = self.ask(self.safe, "resources/read", {"uri": "atena://capabilities"})["result"]["contents"][0]["text"]
        self.assertIn("LA SQUADRA", text)
        self.assertIn("error", self.ask(self.safe, "resources/read", {"uri": "file:///etc/passwd"}))
        self.assertIn("error", self.ask(self.safe, "metodo/inesistente"))
        self.assertIn("error", asyncio.run(mcp.handle({"foo": 1}, self.who(self.safe))))

    def test_calls_run_the_tool_and_report_errors_without_crashing(self):
        reply = self.ask(self.safe, "tools/call", {"name": "agent_info", "arguments": {"agent": "music"}})["result"]
        self.assertFalse(reply["isError"])
        self.assertIn("music_play", reply["content"][0]["text"])
        self.assertTrue(self.ask(self.safe, "tools/call", {"name": "agent_info", "arguments": {}})["result"]["isError"])
        self.assertTrue(self.ask(self.safe, "tools/call", {"name": "agent_info", "arguments": {"agent": "inesistente"}})["result"]["isError"])
        for forbidden, args in (("run_command", {"command": "ls"}), ("read_file", {"path": "x"})):
            self.assertIn("error", self.ask(self.safe, "tools/call", {"name": forbidden, "arguments": args}))

    def test_risky_actions_need_a_risky_token_and_an_explicit_confirmation(self):
        args = {"agent": "music", "key": "ATENA_PASSWORD", "value": "x"}
        refused = self.ask(self.risky, "tools/call", {"name": "agent_set", "arguments": args})["result"]
        self.assertTrue(refused["isError"])
        self.assertIn("_confirm", refused["content"][0]["text"])
        confirmed = self.ask(self.risky, "tools/call", {"name": "agent_set", "arguments": {**args, "_confirm": True}})["result"]
        self.assertIn("non ha l'impostazione", confirmed["content"][0]["text"])
        delegated = self.ask(self.safe, "tools/call", {"name": "agent_ask", "arguments": {"agent": "agent", "tool": "run_command", "args": {"command": "ls"}}})
        self.assertIn("error", delegated)


class EndpointTest(TokenBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(api.admin_routes)
        self.client = TestClient(app)

    def post(self, created: dict | None, body):
        headers = {"Authorization": "Bearer " + created["token"]} if created else {}
        return self.client.post("/mcp", json=body, headers=headers)

    def test_the_endpoint_requires_a_valid_token(self):
        self.assertEqual(self.post(None, rpc("ping")).status_code, 401)
        self.assertEqual(self.post({"token": "jv_falso"}, rpc("ping")).status_code, 401)
        answer = self.post(self.safe, rpc("ping"))
        self.assertEqual((answer.status_code, answer.json()["result"]), (200, {}))

    def test_notifications_batches_and_bad_json(self):
        self.assertEqual(self.post(self.safe, rpc("notifications/initialized", ident=None)).status_code, 202)
        batch = self.post(self.safe, [rpc("ping", ident=1), rpc("ping", ident=2)]).json()
        self.assertEqual([r["id"] for r in batch], [1, 2])
        bad = self.client.post("/mcp", content="{non json", headers={"Authorization": "Bearer " + self.safe["token"]})
        self.assertEqual(bad.status_code, 400)


class PromptsAndLimitsTest(TokenBase):
    def ask(self, created: dict, method: str, params: dict | None = None):
        return asyncio.run(mcp.handle(rpc(method, params), self.who(created)))

    def test_prompts_describe_the_team_and_every_agent(self):
        names = [p["name"] for p in self.ask(self.safe, "prompts/list")["result"]["prompts"]]
        self.assertEqual(names, ["panoramica", "agente"])
        overview = self.ask(self.safe, "prompts/get", {"name": "panoramica"})["result"]["messages"][0]["content"]["text"]
        self.assertIn("LA SQUADRA", overview)
        card = self.ask(self.safe, "prompts/get", {"name": "agente", "arguments": {"agente": "music"}})["result"]["messages"][0]["content"]["text"]
        self.assertIn("music_play", card)
        self.assertIn("error", self.ask(self.safe, "prompts/get", {"name": "sconosciuto"}))
        self.assertIn("error", self.ask(self.safe, "prompts/get", {"name": "agente", "arguments": {"agente": "zzz"}}))

    def test_calls_are_audited_and_rate_limited_per_token(self):
        audit.RING.clear()
        audit.CALLS.clear()
        self.ask(self.safe, "tools/call", {"name": "agent_info", "arguments": {"agent": "music"}})
        last = audit.recent()[-1]
        self.assertEqual((last["client"], last["tool"], last["ok"]), ("lettura", "agent_info", True))
        with mock.patch.object(audit, "LIMIT", 2):
            audit.CALLS.clear()
            self.assertNotIn("error", self.ask(self.safe, "ping"))
            self.assertNotIn("error", self.ask(self.safe, "ping"))
            self.assertEqual(self.ask(self.safe, "ping")["error"]["code"], -32000)
            self.assertNotIn("error", self.ask(self.risky, "ping"))

    def test_clients_are_told_when_the_catalog_changes(self):
        from features.forge import assets

        class Request:
            async def is_disconnected(self):
                return False

        async def scenario():
            with mock.patch.object(api, "WATCH_EVERY", 0.01):
                stream = api.changes(Request(), self.who(self.risky))
                first = await stream.__anext__()
                assets.create_feature({"id": "notifica", "name": "Notifica"})
                second = await asyncio.wait_for(stream.__anext__(), 5)
                await stream.aclose()
                return first, second
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        import feature_registry
        for target, name in ((assets, "FEATURE_DIR"), (feature_registry, "USER_DIR")):
            patcher = mock.patch.object(target, name, Path(folder.name))
            patcher.start()
            self.addCleanup(patcher.stop)

        def rescan():
            feature_registry.registry.signature = ""
            feature_registry.registry.scan()
        self.addCleanup(rescan)
        first, second = asyncio.run(scenario())
        self.assertTrue(first.startswith(":"))
        self.assertIn("notifications/tools/list_changed", second)


class OriginTest(TokenBase):
    def test_browsers_from_other_sites_are_refused(self):
        app = FastAPI()
        app.include_router(api.admin_routes)
        client = TestClient(app)
        headers = {"Authorization": "Bearer " + self.safe["token"]}
        evil = client.post("/mcp", json=rpc("ping"), headers={**headers, "Origin": "http://sito-esterno.example"})
        self.assertEqual(evil.status_code, 403)
        same = client.post("/mcp", json=rpc("ping"), headers={**headers, "Origin": "http://testserver"})
        self.assertEqual(same.status_code, 200)


if __name__ == "__main__":
    unittest.main()
