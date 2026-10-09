import unittest

from features.home_assistant.automations import describe, model
from features.home_assistant.automations.demo import DEMO_AUTOMATIONS
from features.home_assistant.automations.model import AutomationError
from features.home_assistant.automations.service import AutomationService

NAMES = {"binary_sensor.porta": "Porta ingresso", "light.ingresso": "Luce ingresso"}


def name(ref):
    return NAMES.get(ref, ref)


class FakeBrain:
    entities = {"light.ingresso": {"name": "Luce ingresso"}, "binary_sensor.porta": {"name": "Porta ingresso"}}
    states: dict = {}
    areas: dict = {}


class NormalizeTest(unittest.TestCase):
    def test_legacy_singular_keys_become_plural(self):
        out = model.normalize({"alias": "x", "trigger": {"platform": "state", "entity_id": "binary_sensor.porta"},
                               "action": [{"service": "light.turn_on", "target": {"entity_id": "light.ingresso"}}]})
        self.assertEqual(len(out["triggers"]), 1)
        self.assertEqual(out["conditions"], [])
        self.assertEqual(out["mode"], "single")

    def test_rejects_missing_parts(self):
        for raw in ({}, {"alias": "x", "triggers": [{"trigger": "time", "at": "07:00"}]},
                    {"alias": "", "triggers": [{}], "actions": [{}]}, "string", {"alias": "x", "mode": "boom",
                                                                               "triggers": [{}], "actions": [{}]}):
            with self.assertRaises(AutomationError):
                model.normalize(raw)

    def test_rejects_hostile_payloads(self):
        deep: dict = {"a": 1}
        for _ in range(20):
            deep = {"n": deep}
        base = {"alias": "x", "triggers": [{"trigger": "time", "at": "07:00"}]}
        for actions in ([deep], [{"bad key!": 1}], [{"x": "y" * 5000}], [object()]):
            with self.assertRaises(AutomationError):
                model.normalize({**base, "actions": actions})

    def test_ids(self):
        self.assertEqual(model.check_id("1728000000001"), "1728000000001")
        for bad in ("../x", "", "a" * 65, "a b"):
            with self.assertRaises(AutomationError):
                model.check_id(bad)
        with self.assertRaises(AutomationError):
            model.check_entity("light.x")

    def test_entity_ids_are_collected_everywhere(self):
        refs = model.entity_ids(DEMO_AUTOMATIONS[1])
        self.assertEqual(refs, {"cover.tapparella_soggiorno", "cover.tapparella_camera"})


class DescribeTest(unittest.TestCase):
    def test_human_summary(self):
        config = {"triggers": [{"trigger": "state", "entity_id": "binary_sensor.porta", "to": "on", "for": {"minutes": 2}}],
                  "conditions": [{"condition": "time", "after": "23:00:00", "weekday": ["sat", "sun"]}],
                  "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.ingresso"}},
                              {"delay": {"minutes": 5}}, {"action": "notify.notify", "data": {"message": "Ciao"}}]}
        s = describe.summary(config, name)
        self.assertEqual(s["when"], ["Porta ingresso diventa acceso per 2 min"])
        self.assertEqual(s["only_if"], ["dopo le 23:00 (sab, dom)"])
        self.assertEqual(s["then"], ["accendi Luce ingresso", "aspetta 5 min", "invia la notifica «Ciao»"])

    def test_unknown_shapes_never_crash(self):
        s = describe.summary({"trigger": ["{{ x }}", {"platform": "mystery"}], "action": [{"weird": 1}, "x"]}, name)
        self.assertEqual(len(s["when"]), 2)
        self.assertEqual(len(s["then"]), 2)


class DemoServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_crud_cycle_in_demo_mode(self):
        service = AutomationService(FakeBrain())
        rows = await service.overview()
        self.assertEqual(len(rows), len(DEMO_AUTOMATIONS))
        self.assertTrue(all(r["summary"]["when"] for r in rows))
        saved = await service.save(None, {"alias": "Nuova", "triggers": [{"trigger": "time", "at": "08:00"}],
                                          "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.ghost"}}]})
        self.assertEqual(saved["unknown_entities"], ["light.ghost"])
        eid = f"automation.{saved['id']}"
        await service.toggle(eid, False)
        self.assertEqual((await service.get(eid))["state"], "off")
        await service.run(eid)
        self.assertTrue((await service.get(eid))["last_triggered"])
        await service.delete(saved["id"])
        self.assertEqual(len(await service.overview()), len(DEMO_AUTOMATIONS))


if __name__ == "__main__":
    unittest.main()
