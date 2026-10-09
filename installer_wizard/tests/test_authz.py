import asyncio
import json
import time
import unittest
from unittest import mock

from state import store

from features.agent import registry
from features.authz import gate, resolve
from features.authz.heard import HeardLog, heard
from features.authz.policy import Policy, policy
from features.authz.principal import ANONYMOUS, SYSTEM, Principal, Strength, act_as, current
from features.authz.risk import Risk

PROFILES = {
    "nunzio": {"slug": "nunzio", "role": "owner"},
    "anna": {"slug": "anna", "role": "family"},
    "marco": {"slug": "marco", "role": "guest", "authorization": "files"},
}


def _face(slug, confidence=0.9, state="live", known=True):
    return {"slug": slug, "known": known, "confidence": confidence, "liveness": {"state": state}}


class HeardLogTests(unittest.TestCase):

    def test_tap_records_transcripts_from_the_ear_service(self):
        log = HeardLog()
        log.tap(json.dumps({"type": "transcript", "text": "Spegni la luce!", "speaker": "anna", "speaker_score": 0.8}))
        self.assertEqual(log.verify("anna", "spegni la luce").score, 0.8)

    def test_a_client_cannot_claim_a_voice_that_was_not_heard(self):
        log = HeardLog()
        log.record("anna", 0.8, "spegni la luce")
        self.assertIsNone(log.verify("nunzio", "spegni la luce"))
        self.assertIsNone(log.verify("anna", "cancella tutti i file"))
        self.assertIsNone(log.verify("anna", ""))

    def test_old_transcripts_expire(self):
        log = HeardLog()
        log.record("anna", 0.8, "ciao", at=time.time() - 120)
        self.assertIsNone(log.verify("anna", "ciao"))


class ResolveTests(unittest.TestCase):

    def setUp(self):
        self.saved_presence = store.presence
        heard._items.clear()
        self.load = mock.patch.object(resolve, "_profile", side_effect=PROFILES.get).start()
        mock.patch.object(resolve, "_owner", return_value=PROFILES["nunzio"]).start()
        mock.patch.object(resolve, "voice_strong", return_value=0.68).start()

    def tearDown(self):
        mock.patch.stopall()
        store.presence = self.saved_presence

    def test_voice_and_live_face_together_are_strong(self):
        store.presence = {"people": [_face("nunzio")]}
        heard.record("nunzio", 0.7, "esegui il backup")
        who = resolve.for_request("kiosk", "nunzio", "esegui il backup")
        self.assertEqual((who.slug, who.role, who.strength), ("nunzio", "owner", Strength.STRONG))

    def test_confident_voice_alone_is_single(self):
        store.presence = {"people": []}
        heard.record("anna", 0.75, "leggi il file")
        self.assertEqual(resolve.for_request("kiosk", "anna", "leggi il file").strength, Strength.SINGLE)

    def test_borderline_voice_alone_is_weak(self):
        store.presence = {"people": []}
        heard.record("anna", 0.63, "leggi il file")
        self.assertEqual(resolve.for_request("kiosk", "anna", "leggi il file").strength, Strength.WEAK)

    def test_claimed_speaker_without_ear_proof_is_anonymous(self):
        store.presence = {"people": []}
        self.assertEqual(resolve.for_request("kiosk", "nunzio", "cancella tutto"), ANONYMOUS)

    def test_single_live_face_without_voice_is_single(self):
        store.presence = {"people": [_face("anna")]}
        who = resolve.for_request("kiosk", "", "mostrami i documenti")
        self.assertEqual((who.slug, who.strength, who.factors), ("anna", Strength.SINGLE, ("face",)))

    def test_face_is_ignored_when_a_stranger_is_present(self):
        store.presence = {"people": [_face("anna"), _face("", known=False)]}
        self.assertEqual(resolve.for_request("kiosk", "", "mostrami i documenti"), ANONYMOUS)

    def test_spoofed_or_weak_faces_do_not_count(self):
        store.presence = {"people": [_face("anna", state="spoof")]}
        self.assertEqual(resolve.for_request("kiosk", "", "x"), ANONYMOUS)
        store.presence = {"people": [_face("anna", confidence=0.3)]}
        self.assertEqual(resolve.for_request("kiosk", "", "x"), ANONYMOUS)

    def test_authenticated_panel_session_acts_as_the_owner(self):
        who = resolve.for_request("admin", "", "qualsiasi cosa")
        self.assertEqual((who.slug, who.strength, who.factors), ("nunzio", Strength.STRONG, ("session",)))

    def test_person_override_comes_from_the_profile(self):
        store.presence = {"people": [_face("marco")]}
        self.assertEqual(resolve.for_request("kiosk", "", "x").override, "files")


class PolicyTests(unittest.TestCase):

    def setUp(self):
        self.policy = Policy()
        self.policy.apply({})

    def who(self, role, strength, override=""):
        return Principal(slug="x", role=role, strength=strength, override=override)

    def test_owner_needs_face_and_voice_for_critical_actions(self):
        self.assertFalse(self.policy.check(self.who("owner", Strength.SINGLE), Risk.CRITICAL).allowed)
        self.assertTrue(self.policy.check(self.who("owner", Strength.STRONG), Risk.CRITICAL).allowed)

    def test_family_cannot_do_critical_actions_even_when_certain(self):
        decision = self.policy.check(self.who("family", Strength.STRONG), Risk.CRITICAL)
        self.assertEqual((decision.allowed, decision.code), (False, "role"))

    def test_anyone_can_use_the_home(self):
        self.assertTrue(self.policy.check(ANONYMOUS, Risk.HOME).allowed)
        self.assertFalse(self.policy.check(ANONYMOUS, Risk.PERSONAL).allowed)

    def test_personal_override_raises_or_lowers_the_ceiling(self):
        self.assertTrue(self.policy.check(self.who("guest", Strength.SINGLE, "files"), Risk.FILES).allowed)
        self.assertFalse(self.policy.check(self.who("owner", Strength.STRONG, "home"), Risk.PERSONAL).allowed)

    def test_critical_proof_cannot_be_weakened_by_configuration(self):
        self.policy.apply({"proof": {"critical": "none", "personal": "none"}, "ceiling": {"system": "info"}})
        self.assertEqual(self.policy.export()["proof"]["critical"], "strong")
        self.assertEqual(self.policy.export()["proof"]["personal"], "weak")
        self.assertEqual(self.policy.export()["ceiling"]["system"], "critical")


class EnforcementTests(unittest.TestCase):

    def tearDown(self):
        policy.apply({})

    def run_as(self, principal, coro):
        async def go():
            act_as(principal)
            return await coro()
        return asyncio.run(go())

    def test_runner_refuses_critical_tools_without_strong_proof(self):
        from features.team import runner
        weak_owner = Principal(slug="nunzio", role="owner", strength=Strength.SINGLE)
        with mock.patch.object(runner, "execute") as execute:
            with self.assertRaises(gate.Forbidden):
                self.run_as(weak_owner, lambda: runner.run_as("run_command", {"command": "rm -rf /"}))
        execute.assert_not_called()

    def test_unknown_tools_are_treated_as_critical(self):
        act_as(Principal(slug="anna", role="family", strength=Strength.STRONG))
        self.assertFalse(gate.tool("nuovo_strumento").allowed)
        current.set(ANONYMOUS)

    def test_agent_explains_instead_of_executing(self):
        from features.agent.agent import Agent
        agent = Agent()
        move = {"tool": "run_command", "args": {"command": "ls"}}
        with mock.patch.object(agent, "_decide", return_value=move), mock.patch.object(agent, "_execute") as execute, \
                mock.patch.object(gate, "within_role", return_value=True), \
                mock.patch.object(registry, "available", return_value=[{"name": "run_command"}]):
            reply = self.run_as(Principal(slug="nunzio", role="owner", strength=Strength.SINGLE), lambda: agent.run("lista i file"))
        execute.assert_not_called()
        self.assertIn("volto e voce", reply)

    def test_automations_run_as_atena_and_restore_the_caller(self):
        from features.agent.agent import Agent
        agent = Agent()
        seen = []

        async def decide(request, steps):
            seen.append(current.get())
            return {"answer": "fatto"}

        with mock.patch.object(agent, "_decide", side_effect=decide):
            self.run_as(ANONYMOUS, lambda: agent.run("routine", auto="Automazione: luci"))
        self.assertEqual(seen, [SYSTEM])
        self.assertEqual(current.get(), ANONYMOUS)

    def test_tools_beyond_the_role_are_hidden_from_the_model(self):
        act_as(Principal(slug="ospite", role="guest", strength=Strength.STRONG))
        self.assertFalse(gate.within_role("run_command"))
        self.assertTrue(gate.within_role("show_widget"))
        current.set(ANONYMOUS)

    def test_personal_connectors_need_recognition(self):
        from features.chat import assistant
        act_as(ANONYMOUS)
        refused = assistant._refused("vault", time.time())
        self.assertEqual(refused["intent"], "authz")
        self.assertIsNone(assistant._refused("music", time.time()))
        act_as(Principal(slug="anna", role="family", strength=Strength.SINGLE))
        self.assertIsNone(assistant._refused("vault", time.time()))
        current.set(ANONYMOUS)


class CatalogCoverageTests(unittest.TestCase):

    def test_tools_built_by_atena_inherit_the_riskiest_step(self):
        from features.authz import risk
        risk.compose("zz_saluta", ["show_widget", "now"])
        risk.compose("zz_pulizia", ["show_widget", "delete"])
        risk.compose("zz_loop", ["zz_loop"])
        self.assertEqual(risk.of_tool("zz_saluta"), Risk.HOME)
        self.assertEqual(risk.of_tool("zz_pulizia"), Risk.CRITICAL)
        self.assertEqual(risk.of_tool("zz_loop"), Risk.CRITICAL)
        for name in ("zz_saluta", "zz_pulizia", "zz_loop"):
            risk.forget(name)

    def test_every_registered_tool_has_an_explicit_risk(self):
        from features.agent import agent
        from features.authz.risk import TOOLS
        self.assertTrue(agent.MODULES)
        missing = sorted(set(registry.TOOLS) - set(TOOLS))
        self.assertEqual(missing, [], "classify these tools in features/authz/risk.py")


if __name__ == "__main__":
    unittest.main()
