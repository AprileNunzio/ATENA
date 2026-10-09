import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import atena_supervisor
from features.flows import composition
from features.flows.application.studio import ConfirmationRequired, Studio
from features.flows.domain import draft, guard
from features.flows.domain.catalog import EDGES, NODE_BY_ID, NODES, TEMPLATES, defaults, template
from features.flows.infrastructure.env_settings import MIXED, EnvSettings
from features.flows.infrastructure.signed_store import SignedVersionStore

HEADERS = {"X-Atena-Request": "1"}
DEFAULT_SETTINGS = {"understanding.enabled": "1", "understanding.arbiter": "1", "skills.enabled": "1", "skills.generate": "1",
                    "memory.enabled": "1", "agent.enabled": "1", "agent.access": "completo", "brain.strategy": "order",
                    "brain.scope": "anywhere", "presentation.mode": "smart"}


class CatalogTest(unittest.TestCase):
    def test_every_node_has_exactly_one_default_and_a_chain(self):
        for node in NODES:
            self.assertEqual(sum(a.default for a in node.algorithms), 1, node.id)
            self.assertTrue(node.default.available, node.id)
        self.assertEqual(len(EDGES), len(NODES) - 1)
        self.assertTrue(NODE_BY_ID["laws"].locked)

    def test_templates_only_use_available_algorithms(self):
        for name in TEMPLATES:
            for nid, aid in template(name).items():
                algorithm = NODE_BY_ID[nid].algorithm(aid)
                self.assertIsNotNone(algorithm, (name, nid))
                self.assertTrue(algorithm.available, (name, nid))
        with self.assertRaises(ValueError):
            template("nope")


class DraftDomainTest(unittest.TestCase):
    def test_infer_round_trips_through_effects(self):
        self.assertEqual(draft.infer(DEFAULT_SETTINGS), defaults())
        for name in TEMPLATES:
            picks = template(name)
            settings = {**DEFAULT_SETTINGS, **draft.effects(picks)}
            self.assertEqual(draft.infer(settings), picks, name)
        self.assertEqual(draft.infer({**DEFAULT_SETTINGS, "brain.scope": MIXED})["brain"], draft.CUSTOM)

    def test_parse_rejects_unsafe_drafts(self):
        current = defaults()
        for bad in ([], {"picks": "x"}, {"picks": {"ghost": "x"}}, {"picks": {"brain": "brain.nope"}},
                    {"picks": {"reasoning": "reasoning.tot"}}, {"picks": {"laws": "brain.order"}},
                    {"positions": {"brain": [0, 0]}}, {"positions": {"brain": ["a", 1]}}, {"template": "evil"}):
            with self.assertRaises(ValueError, msg=bad):
                draft.parse(bad, current)

    def test_custom_pick_keeps_what_is_configured(self):
        current = {**defaults(), "brain": draft.CUSTOM}
        parsed = draft.parse({"picks": {"brain": draft.CUSTOM}}, current)
        self.assertEqual(parsed.picks["brain"], draft.CUSTOM)
        self.assertNotIn("brain.scope", draft.effects(parsed.picks))

    def test_changes_traits_and_estimate(self):
        picks = template("private")
        self.assertEqual(draft.changes(picks, DEFAULT_SETTINGS),
                         {"brain.scope": "home", "agent.access": "standard"})
        self.assertGreater(draft.traits(picks)["privacy"], draft.traits(defaults())["privacy"])
        fast, precise = sum(s["seconds"] for s in draft.estimate(template("fast"))), sum(s["seconds"] for s in draft.estimate(defaults()))
        self.assertLess(fast, precise)


class EnvSettingsTest(unittest.TestCase):
    def test_reads_defaults_and_expands_roles(self):
        settings = EnvSettings(lambda: {}, None)
        self.assertEqual(settings.read(), DEFAULT_SETTINGS)
        env = settings.env_updates({"brain.scope": "home", "understanding.arbiter": "0"})
        self.assertEqual(env["ATENA_UNDERSTANDING_LLM"], "0")
        self.assertIn("ATENA_LLM_CHAT_SCOPE", env)
        self.assertTrue(all(v == "home" for k, v in env.items() if k.endswith("_SCOPE")))
        with self.assertRaises(ValueError):
            settings.env_updates({"rm.rf": "1"})

    def test_mixed_roles_are_reported(self):
        self.assertEqual(EnvSettings(lambda: {"ATENA_LLM_CHAT_STRATEGY": "fastest"}, None).read()["brain.strategy"], MIXED)


class SignedStoreTest(unittest.TestCase):
    def test_versions_are_signed_and_tampering_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, key = Path(tmp) / "main.json", Path(tmp) / "flows.key"
            store = SignedVersionStore(path, key)
            self.assertEqual(store.append({"picks": {"brain": "brain.home"}})["version"], 1)
            self.assertEqual(store.append({"picks": {"brain": "brain.order"}})["version"], 2)
            self.assertEqual([v["version"] for v in store.versions()], [2, 1])
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            doc = json.loads(path.read_text())
            doc["versions"][0]["picks"]["brain"] = "brain.fastest"
            path.write_text(json.dumps(doc))
            self.assertEqual([v["version"] for v in store.versions()], [2])


class FakeSettings:
    def __init__(self):
        self.values = dict(DEFAULT_SETTINGS)
        self.applied = []

    def read(self):
        return dict(self.values)

    async def apply(self, updates, user):
        self.applied.append(updates)
        self.values.update(updates)
        return []


class FakeVerifier:
    async def confirm(self, user, password, ip):
        return password == "giusta"


class StudioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = FakeSettings()
        self.studio = Studio(self.settings, SignedVersionStore(Path(self.tmp.name) / "m.json", Path(self.tmp.name) / "k"),
                             FakeVerifier(), clock=lambda: 100.0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_publish_requires_password_and_applies_changes(self):
        self.studio.save_draft({"picks": template("private"), "template": "private"})
        for wrong in (None, "", "sbagliata", 123):
            with self.assertRaises(ConfirmationRequired):
                asyncio.run(self.studio.publish("anna", wrong, "1.2.3.4"))
        self.assertEqual(self.settings.applied, [])
        result = asyncio.run(self.studio.publish("anna", "giusta", "1.2.3.4"))
        self.assertEqual(result["changed"], ["agent.access", "brain.scope"])
        self.assertEqual(self.studio.studio()["current"]["brain"], "brain.home")
        self.assertEqual(self.studio.studio()["pending"], {})

    def test_rollback_restores_an_older_version(self):
        self.studio.save_draft({"picks": template("fast")})
        asyncio.run(self.studio.publish("anna", "giusta", "-"))
        self.studio.save_draft({"picks": template("private")})
        asyncio.run(self.studio.publish("anna", "giusta", "-"))
        asyncio.run(self.studio.rollback(1, "anna", "giusta", "-"))
        self.assertEqual(self.studio.studio()["current"]["brain"], "brain.fastest")
        with self.assertRaises(LookupError):
            asyncio.run(self.studio.rollback(99, "anna", "giusta", "-"))


class GuardTest(unittest.TestCase):
    def test_rollback_only_with_enough_failures_in_the_window(self):
        bad = [(110.0, "failed")] * 3 + [(120.0, "done")]
        self.assertTrue(guard.should_rollback(bad, 100.0, 200.0))
        self.assertFalse(guard.should_rollback(bad[:3], 100.0, 200.0))
        self.assertFalse(guard.should_rollback([(110.0, "done")] * 3 + [(111.0, "failed")], 100.0, 200.0))
        self.assertFalse(guard.should_rollback(bad, 100.0, 100.0 + guard.WATCH_SECONDS + 1))
        self.assertFalse(guard.should_rollback([(50.0, "failed")] * 9, 100.0, 200.0))
        self.assertFalse(guard.should_rollback([(110.0, "running")] * 9, 100.0, 200.0))


class SafeguardTest(StudioTest):
    def test_too_many_failures_restore_the_previous_version_once(self):
        clock = [100.0]
        self.studio.clock = lambda: clock[0]
        self.studio.save_draft({"picks": template("private")})
        asyncio.run(self.studio.publish("anna", "giusta", "-"))
        self.studio.save_draft({"picks": template("fast")})
        clock[0] = 200.0
        asyncio.run(self.studio.publish("anna", "giusta", "-"))
        failures = [(210.0, "failed")] * 4
        clock[0] = 260.0
        result = asyncio.run(self.studio.safeguard(failures))
        self.assertTrue(result["version"]["auto"])
        self.assertEqual(self.studio.studio()["current"]["brain"], "brain.home")
        self.assertIsNone(asyncio.run(self.studio.safeguard(failures)))

    def test_compare_reports_differences(self):
        data = self.studio.compare({"a": {"picks": template("fast")}, "b": {"picks": template("private")}})
        self.assertIn("brain", data["different"])
        self.assertGreater(data["b"]["traits"]["privacy"], data["a"]["traits"]["privacy"])
        for bad in ({}, {"a": "x", "b": {}}, {"a": {"picks": {"laws": "x"}}, "b": {}}):
            with self.assertRaises(ValueError):
                self.studio.compare(bad)


class FlowsApiTest(unittest.TestCase):
    def test_endpoints(self):
        self.assertEqual(TestClient(atena_supervisor.admin).get("/api/flows/studio").status_code, 401)
        admin = TestClient(atena_supervisor.admin)
        admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        tmp = Path(tempfile.mkdtemp())
        with mock.patch.object(composition.studio, "store", SignedVersionStore(tmp / "m.json", tmp / "k")):
            data = admin.get("/api/flows/studio").json()
            self.assertEqual(len(data["nodes"]), len(NODES))
            self.assertEqual(admin.put("/api/flows/draft", json={"picks": {"brain": "brain.home"}}).status_code, 403)
            r = admin.put("/api/flows/draft", json={"picks": {"brain": "brain.home"}}, headers=HEADERS)
            self.assertEqual(r.json()["pending"].get("brain.scope"), "home")
            self.assertEqual(admin.put("/api/flows/draft", json={"picks": {"laws": "x"}}, headers=HEADERS).status_code, 400)
            self.assertEqual(admin.post("/api/flows/publish", json={"password": "no"}, headers=HEADERS).status_code, 403)
            self.assertEqual(admin.post("/api/flows/rollback/42", json={"password": "atena"}, headers=HEADERS).status_code, 404)
            self.assertEqual(admin.delete("/api/flows/draft", headers=HEADERS).json()["pending"], {})
            r = admin.post("/api/flows/compare", json={"a": {"picks": {}}, "b": {"picks": {"brain": "brain.home"}}}, headers=HEADERS)
            self.assertEqual(r.json()["different"], ["brain"])


if __name__ == "__main__":
    unittest.main()
