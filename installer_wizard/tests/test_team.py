import asyncio
import unittest
from unittest import mock

from features.agent import registry
from features.capabilities import manifest
from features.team import roster, runner
from features.team import tools as team_tools
from features.team.board import Board, board


def call(tool_name: str, **args) -> str:
    return asyncio.run(registry.run(tool_name, args))


class RosterTest(unittest.TestCase):
    def setUp(self):
        board.doing.clear()
        board.claims.clear()
        board.inbox.clear()
        board.messages.clear()

    def test_every_feature_is_an_agent_ordered_by_priority(self):
        ids = roster.ids()
        self.assertIn("music", ids)
        self.assertIn("laws", ids)
        self.assertLess(ids.index("laws"), ids.index("music"))
        profile = roster.profile("music")
        self.assertEqual(profile["priority"], 30)
        self.assertTrue(profile["settings"] and profile["can"])
        self.assertIn("music_play", {t["name"] for t in profile["tools"]})
        self.assertIn("open_camera", {t["name"] for t in roster.profile("cameras")["tools"]})
        self.assertEqual(roster.owner("show_widget"), "desktop")
        self.assertEqual(roster.find("music"), "music")

    def test_the_prompt_lists_the_team_with_priorities(self):
        text = manifest.summary()
        self.assertIn("LA SQUADRA", text)
        self.assertIn("music_play", text)
        self.assertLess(len(text), 20000)


class BoardTest(unittest.TestCase):
    def test_activity_messages_and_inbox(self):
        b = Board()
        b.begin("music", "music_play luna")
        self.assertEqual(b.current()["music"]["what"], "music_play luna")
        b.post("music", "cameras", "abbassa lo schermo")
        self.assertEqual(b.read("cameras")[0]["text"], "abbassa lo schermo")
        self.assertEqual(b.read("cameras"), [])
        b.end("music", "ok")
        self.assertEqual(b.current(), {})
        self.assertIn("music → tutti", b.digest())

    def test_the_higher_priority_agent_keeps_a_resource(self):
        b = Board()
        self.assertIsNone(b.claim("laws", "audio:sala"))
        self.assertEqual(b.claim("music", "audio:sala"), "laws")
        self.assertIsNone(b.claim("music", "audio:cucina"))
        self.assertIsNone(b.claim("laws", "audio:cucina"))
        self.assertEqual(b.claims["audio:cucina"]["agent"], "laws")
        b.release("laws", "audio:sala")
        self.assertIsNone(b.claim("music", "audio:sala"))


class CollaborationTest(unittest.TestCase):
    def setUp(self):
        board.doing.clear()
        board.messages.clear()
        board.inbox.clear()

    def test_tools_report_their_work_on_the_board(self):
        seen = {}

        async def probe() -> str:
            seen.update(board.current())
            return "fatto"
        registry.TOOLS["zz_probe"] = {"name": "zz_probe", "description": "", "args": {}, "fn": probe, "confirm": False, "full_only": False, "agent": "music"}
        self.addCleanup(registry.TOOLS.pop, "zz_probe")
        self.assertEqual(asyncio.run(runner.run_as("zz_probe", {})), "fatto")
        self.assertIn("music", seen)
        self.assertEqual(board.current(), {})
        self.assertEqual(board.messages[-1]["kind"], "esito")

    def test_agents_talk_and_delegate_to_the_owner_of_a_tool(self):
        self.assertIn("consegnato", call("agent_tell", to="music", text="stasera cena"))
        self.assertIn("stasera cena", call("agent_inbox", agent="music"))
        self.assertEqual(call("agent_inbox", agent="music"), "nessun messaggio")
        info = call("agent_info", agent="music")
        self.assertIn("music_play", info)
        self.assertIn("priorità 30", info)
        self.assertIn("music", call("team_roster"))
        with self.assertRaises(ValueError):
            call("agent_ask", agent="cameras", tool="music_play", args={})
        with self.assertRaises(ValueError):
            call("agent_ask", agent="agent", tool="agent_set", args={})
        with mock.patch.object(team_tools.runner, "run_as", mock.AsyncMock(return_value="suona")) as run:
            self.assertEqual(call("agent_ask", agent="music", tool="music_now"), "suona")
        run.assert_awaited_once()
        self.assertEqual(board.messages[-1]["kind"], "richiesta")

    def test_delegation_keeps_the_confirmation_of_the_original_tool(self):
        self.assertTrue(registry.needs_confirm("agent_ask", {"tool": "run_command", "args": {"command": "rm x"}}))
        self.assertFalse(registry.needs_confirm("agent_ask", {"tool": "music_now", "args": {}}))
        self.assertTrue(registry.needs_confirm("agent_ask", {"tool": "inesistente"}))
        self.assertTrue(registry.needs_confirm("agent_set", {}))

    def test_settings_can_only_be_changed_through_declared_keys(self):
        with self.assertRaises(ValueError):
            call("agent_set", agent="music", key="ATENA_PASSWORD", value="x")
        apply = mock.AsyncMock(return_value=[])
        with mock.patch("settings.apply_config", apply):
            key = roster.profile("music")["settings"][0]
            options = key["options"]
            value = options[0] if options else "1"
            call("agent_set", agent="music", key=key["key"], value=value)
        apply.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
