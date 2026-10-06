import unittest

from features.twin.model import HomeState, predicted_state
from features.twin.rules import RULES
from features.twin.simulator import review, simulate

ALL = list(RULES)


def home(**over):
    states = {"alarm_control_panel.casa": {"state": "disarmed"}, "camera.esterna": {"state": "idle"},
              "switch.telecamere_giardino": {"state": "on", "attrs": {"friendly_name": "Telecamere giardino"}},
              "lock.ingresso": {"state": "locked"}, "light.sala": {"state": "on"}, "climate.sala": {"state": "off", "attrs": {"area_id": "sala"}},
              "binary_sensor.finestra_sala": {"state": "on", "attrs": {"device_class": "window", "area_id": "sala"}},
              "valve.acqua": {"state": "closed"}, "cover.garage": {"state": "closed"}}
    states.update(over)
    return HomeState(states, {"people": 1})


def call(service, *entities, **data):
    domain, name = service.split(".")
    return {"domain": domain, "service": name, "entity_ids": list(entities), "data": data}


class EffectTest(unittest.TestCase):
    def test_predicted_states(self):
        self.assertEqual(predicted_state("lock.x", "unlock", {}, "locked"), "unlocked")
        self.assertEqual(predicted_state("lock.x", "toggle", {}, "locked"), "unlocked")
        self.assertEqual(predicted_state("cover.x", "set_cover_position", {"position": 0}, "open"), "closed")
        self.assertEqual(predicted_state("climate.x", "set_hvac_mode", {"hvac_mode": "heat"}, "off"), "heat")
        self.assertEqual(predicted_state("alarm_control_panel.x", "alarm_arm_night", {}, "disarmed"), "armed_night")
        self.assertEqual(predicted_state("camera.x", "turn_off", {}, "idle"), "off")


class NightPlanTest(unittest.TestCase):
    def test_prepare_for_night_drops_only_the_dangerous_calls(self):
        plan = {"calls": [call("light.turn_off", "light.sala"), call("alarm_control_panel.alarm_arm_night", "alarm_control_panel.casa"),
                          call("switch.turn_off", "switch.telecamere_giardino"), call("lock.unlock", "lock.ingresso")]}
        result = review(home(), plan, ALL)
        self.assertEqual({d["entity"] for d in result.dropped}, {"switch.telecamere_giardino", "lock.ingresso"})
        self.assertEqual([c["entity_ids"] for c in result.plan["calls"]], [["light.sala"], ["alarm_control_panel.casa"]])
        self.assertFalse(result.blocked)

    def test_warn_mode_keeps_the_plan_but_reports(self):
        plan = {"calls": [call("alarm_control_panel.alarm_arm_away", "alarm_control_panel.casa"), call("camera.turn_off", "camera.esterna")]}
        result = review(home(), plan, ALL, correct=False)
        self.assertTrue(result.blocked)
        self.assertEqual(result.dropped, [])
        self.assertEqual(len(result.plan["calls"]), 2)

    def test_disabled_rules_do_not_fire(self):
        plan = {"calls": [call("alarm_control_panel.alarm_arm_away", "alarm_control_panel.casa"), call("camera.turn_off", "camera.esterna")]}
        self.assertEqual(review(home(), plan, ["valve_unattended"]).dropped, [])


class RuleTest(unittest.TestCase):
    def rules_hit(self, state, plan):
        return {c.rule for c in simulate(state, {"calls": plan}, ALL)[1]}

    def test_unlocking_while_already_armed(self):
        self.assertIn("access_while_armed", self.rules_hit(home(**{"alarm_control_panel.casa": {"state": "armed_away"}}), [call("lock.unlock", "lock.ingresso")]))

    def test_generic_toggle_cannot_bypass(self):
        self.assertIn("access_while_armed", self.rules_hit(home(**{"alarm_control_panel.casa": {"state": "armed_home"}}),
                                                           [call("cover.open_cover", "cover.garage")]))

    def test_arming_with_window_open_is_a_warning(self):
        state = home(**{"cover.garage": {"state": "open"}})
        conflicts = simulate(state, {"calls": [call("alarm_control_panel.alarm_arm_away", "alarm_control_panel.casa")]}, ALL)[1]
        self.assertEqual({(c.rule, c.severity) for c in conflicts}, {("armed_with_open_access", "warn")})

    def test_heating_with_window_open_warns(self):
        self.assertIn("climate_with_open_window", self.rules_hit(home(), [call("climate.set_hvac_mode", "climate.sala", hvac_mode="heat")]))

    def test_valve_with_nobody_home_is_blocked(self):
        empty = HomeState(home().states, {"people": 0})
        result = review(empty, {"calls": [call("valve.open_valve", "valve.acqua")]}, ALL)
        self.assertEqual(result.plan["calls"], [])

    def test_contradictory_calls_keep_the_first(self):
        result = review(home(), {"calls": [call("light.turn_on", "light.sala"), call("light.turn_off", "light.sala")]}, ALL)
        self.assertEqual([(c["service"], c["entity_ids"]) for c in result.plan["calls"]], [("turn_on", ["light.sala"])])

    def test_harmless_plans_pass_untouched(self):
        result = review(home(), {"calls": [call("light.turn_off", "light.sala")]}, ALL)
        self.assertEqual((result.conflicts, result.dropped), ([], []))


if __name__ == "__main__":
    unittest.main()
