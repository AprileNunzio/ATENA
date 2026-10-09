import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import feature_registry
from features.agent import registry
from features.authz.principal import SYSTEM, act_as, current
from features.capabilities import catalog, mcp
from features.desktop import desk as desk_module
from features.desktop.desk import desk
from features.forge import assets, recipes
from features.team import roster
from features.team.board import board


def call(tool_name: str, **args) -> str:
    return asyncio.run(registry.run(tool_name, args))


class ForgeBase(unittest.TestCase):
    def setUp(self):
        self.principal = act_as(SYSTEM)
        self.addCleanup(current.reset, self.principal)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        for target, name, value in ((recipes, "DIR", root / "tools"), (desk_module, "USER_DIR", root / "widgets"),
                                    (assets, "FEATURE_DIR", root / "features"), (feature_registry, "USER_DIR", root / "features")):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        (root / "widgets").mkdir()
        (root / "features").mkdir()
        self.seen = []

        async def echo(text: str = "") -> str:
            self.seen.append(text)
            return f"eco:{text}"

        async def danger(text: str = "") -> str:
            return "fatto"
        for name, fn, confirm in (("zz_echo", echo, False), ("zz_danger", danger, True)):
            registry.TOOLS[name] = {"name": name, "description": "", "args": {"text": "x"}, "fn": fn, "confirm": confirm, "full_only": False, "agent": "music", "verify": None}
            self.addCleanup(registry.TOOLS.pop, name)
        self.addCleanup(lambda: [recipes.remove(n) for n in list(recipes.CUSTOM)])
        board.messages.clear()

        def rescan():
            desk.signature = ""
            feature_registry.registry.signature = ""
            desk.scan()
            feature_registry.registry.scan()
        self.addCleanup(rescan)


class RecipeTest(ForgeBase):
    spec = {"name": "doppio_eco", "description": "ripete due volte", "params": {"frase": "cosa dire"},
            "steps": [{"tool": "zz_echo", "args": {"text": "{{frase}}"}}, {"tool": "zz_echo", "args": {"text": "{{s1}}+{{frase}}"}}]}

    def test_a_new_tool_is_created_listed_run_and_persisted(self):
        self.assertIn("creato", call("create_tool", **self.spec))
        self.assertIn("doppio_eco", call("list_custom_tools"))
        out = call("doppio_eco", frase="ciao")
        self.assertEqual(self.seen, ["ciao", "eco:ciao+ciao"])
        self.assertIn("2. zz_echo: eco:eco:ciao+ciao", out)
        self.assertEqual(board.messages[0]["kind"], "creazione")
        recipes.CUSTOM.clear()
        registry.TOOLS.pop("doppio_eco")
        self.assertEqual(recipes.load(), 1)
        self.assertIn("doppio_eco", registry.TOOLS)
        self.assertTrue(registry.TOOLS["doppio_eco"]["custom"])

    def test_invalid_recipes_are_refused(self):
        bad = [{**self.spec, "name": "X"}, {**self.spec, "name": "run_command"}, {**self.spec, "steps": []},
               {**self.spec, "steps": [{"tool": "non_esiste", "args": {}}]},
               {**self.spec, "steps": [{"tool": "zz_echo", "args": {"text": "{{ignoto}}"}}]},
               {**self.spec, "steps": [{"tool": "zz_echo", "args": {"text": "{{s1}}"}}]},
               {**self.spec, "steps": [{"tool": "zz_echo", "args": {}}] * 11}]
        for spec in bad:
            with self.assertRaises(ValueError, msg=spec):
                call("create_tool", **spec)
        recipes.save(self.spec)
        with self.assertRaises(ValueError):
            recipes.save({**self.spec, "name": "annidato", "steps": [{"tool": "doppio_eco", "args": {}}]})

    def test_a_custom_tool_inherits_the_confirmation_of_its_steps(self):
        recipes.save({"name": "pericoloso", "description": "d", "params": {}, "steps": [{"tool": "zz_danger", "args": {}}]})
        recipes.save(self.spec)
        self.assertTrue(registry.needs_confirm("pericoloso", {}))
        self.assertFalse(registry.needs_confirm("doppio_eco", {"frase": "x"}))

    def test_deleting_needs_confirmation_and_only_touches_custom_tools(self):
        recipes.save(self.spec)
        self.assertTrue(registry.needs_confirm("delete_tool", {"name": "doppio_eco"}))
        self.assertIn("eliminato", call("delete_tool", name="doppio_eco"))
        self.assertNotIn("doppio_eco", registry.TOOLS)
        with self.assertRaises(ValueError):
            call("delete_tool", name="zz_echo")
        self.assertIn("zz_echo", registry.TOOLS)


class AssetsTest(ForgeBase):
    def test_widgets_are_created_shown_and_removed_only_when_made_by_atena(self):
        self.assertIn("creato", call("create_widget", id="termostato", name="Termostato", description="temperatura", size="s"))
        self.assertEqual(desk.widgets["termostato"]["source"], "ai")
        folder = desk_module.USER_DIR / "termostato"
        self.assertIn('register("termostato"', (folder / "widget.js").read_text(encoding="utf-8"))
        self.assertEqual(desk.widgets["termostato"]["size"], "s")
        call("show_widget", id="termostato", data={"title": "Salotto", "value": 21})
        self.assertIn("termostato", {i["id"] for i in desk.active()})
        with self.assertRaises(ValueError):
            call("create_widget", id="live_cam", name="finto")
        with self.assertRaises(ValueError):
            call("create_widget", id="../fuori", name="x")
        self.assertIn("eliminato", call("delete_widget", id="termostato"))
        self.assertFalse(folder.exists())
        self.assertNotIn("termostato", desk.widgets)
        with self.assertRaises(ValueError):
            call("delete_widget", id="live_cam")
        self.assertIn("live_cam", desk.widgets)

    def test_features_become_agents_and_system_ones_are_protected(self):
        self.assertIn("agente", call("create_feature", id="giardino", name="Giardino", description="irrigazione", capabilities=["annaffia"], category="casa"))
        self.assertEqual(feature_registry.registry.features["giardino"]["source"], "ai")
        self.assertIn("giardino", roster.ids())
        self.assertEqual(roster.profile("giardino")["can"], ["annaffia"])
        with self.assertRaises(ValueError):
            call("create_feature", id="music", name="finta")
        with self.assertRaises(ValueError):
            call("delete_feature", id="music")
        self.assertIn("music", feature_registry.registry.features)
        call("delete_feature", id="giardino")
        self.assertNotIn("giardino", feature_registry.registry.features)


class AutoExposureTest(ForgeBase):
    def token(self, risky: bool) -> dict:
        return {"id": "t", "label": "prova", "risky": risky}

    def test_a_tool_made_by_atena_shows_up_in_mcp_without_any_restart(self):
        full = self.token(True)
        before = catalog.signature(mcp.visible(full))
        self.assertNotIn("doppio_eco", mcp.visible(full))
        recipes.save(RecipeTest.spec)
        self.assertIn("doppio_eco", mcp.visible(full))
        self.assertNotEqual(catalog.signature(mcp.visible(full)), before)
        listed = {t["name"]: t for t in mcp.listing(full)["tools"]}
        self.assertEqual(listed["doppio_eco"]["inputSchema"]["properties"]["frase"]["type"], "string")
        reply = asyncio.run(mcp.call({"name": "doppio_eco", "arguments": {"frase": "mcp"}}, full))
        self.assertFalse(reply["isError"])
        self.assertIn("eco:mcp", reply["content"][0]["text"])

    def test_limited_tokens_never_see_what_atena_forges(self):
        recipes.save(RecipeTest.spec)
        self.assertNotIn("doppio_eco", mcp.visible(self.token(False)))
        self.assertNotIn("create_tool", mcp.visible(self.token(False)))
        self.assertIn("create_tool", mcp.visible(self.token(True)))

    def test_new_widgets_and_features_change_the_catalog_and_the_resources(self):
        full = self.token(True)
        before = catalog.signature(mcp.visible(full))
        assets.create_widget({"id": "meteo_extra", "name": "Meteo extra"})
        assets.create_feature({"id": "serra", "name": "Serra"})
        self.assertNotEqual(catalog.signature(mcp.visible(full)), before)
        self.assertIn("meteo_extra", catalog.widgets())
        self.assertIn("atena://agent/serra", [r["uri"] for r in catalog.resources(None)])
        self.assertNotIn("atena://agent/serra", [r["uri"] for r in catalog.resources({"music"})])
        self.assertIn("Serra", catalog.read("atena://agent/serra")[1])


if __name__ == "__main__":
    unittest.main()
