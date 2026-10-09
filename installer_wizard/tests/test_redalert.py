import asyncio
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from features.desktop import api as desk_api
from features.home_assistant.home import brain
from features.redalert import api as red_api
from features.redalert import broadcast, lights, service
from features.redalert.service import RedAlert

STATES = {
    "light.sala": {"state": "on", "attrs": {"brightness": 120, "color_temp_kelvin": 3000, "friendly_name": "Sala"}},
    "light.cucina": {"state": "off", "attrs": {}},
    "light.rotta": {"state": "unavailable", "attrs": {}},
    "switch.presa": {"state": "on", "attrs": {}},
}


class LightsTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

        async def call(payload, timeout=20):
            self.calls.append((payload["service"], tuple(payload["target"]["entity_id"]), payload["service_data"]))

        for p in (mock.patch.object(brain, "states", STATES), mock.patch.object(brain, "status", "online"),
                  mock.patch.object(brain, "_call", side_effect=call), mock.patch.object(lights, "PERIOD", 0.01)):
            p.start()
            self.addCleanup(p.stop)

    def test_snapshot_skips_unavailable_and_non_lights(self):
        self.assertEqual(sorted(lights.snapshot()), ["light.cucina", "light.sala"])

    def test_flash_then_restore_exact_previous_state(self):
        saved = lights.snapshot()

        async def run():
            stop = asyncio.Event()
            asyncio.get_running_loop().call_later(0.05, stop.set)
            return await lights.flash(list(saved), stop, 5)

        self.assertGreaterEqual(asyncio.run(run()), 1)
        self.assertEqual(self.calls[0], ("turn_on", ("light.sala", "light.cucina"), {"rgb_color": [255, 0, 0], "brightness": 255}))
        self.calls.clear()
        asyncio.run(lights.restore(saved))
        self.assertIn(("turn_off", ("light.cucina",), {}), self.calls)
        self.assertIn(("turn_on", ("light.sala",), {"brightness": 120, "color_temp_kelvin": 3000}), self.calls)


class ServiceTest(unittest.TestCase):
    def test_trigger_flashes_announces_and_restores_on_stop(self):
        alert = RedAlert()
        flashed, restored, said = [], [], []

        async def flash(entities, stop, seconds):
            flashed.append(entities)
            await stop.wait()

        async def restore(saved):
            restored.append(saved)

        async def announce(text):
            said.append(text)
            return ["Salotto"]

        env = {"ATENA_REDALERT": "1"}
        with mock.patch.object(service, "env_get", side_effect=lambda k, d="": env.get(k, d)), \
                mock.patch.object(lights, "snapshot", return_value={"light.sala": {"on": True}}), \
                mock.patch.object(lights, "flash", side_effect=flash), mock.patch.object(lights, "restore", side_effect=restore), \
                mock.patch.object(broadcast, "announce", side_effect=announce):
            async def run():
                self.assertTrue(alert.trigger("Fumo in cucina"))
                self.assertTrue(alert.trigger("di nuovo"))
                await asyncio.sleep(0.05)
                alert.stop()
                await alert.task
            asyncio.run(run())
        self.assertEqual(flashed, [["light.sala"]])
        self.assertEqual(said, ["di nuovo"])
        self.assertEqual(restored, [{"light.sala": {"on": True}}])

    def test_disabled(self):
        with mock.patch.object(service, "env_get", return_value="0"):
            self.assertFalse(RedAlert().trigger("x"))


class RoutesTest(unittest.TestCase):
    def test_audio_clip_is_one_token_and_expires(self):
        app = FastAPI()
        app.include_router(red_api.public_routes)
        http = TestClient(app)
        token = broadcast.clips.add(b"RIFFdata")
        self.assertEqual(http.get(f"/api/redalert/audio/{token}.wav").content, b"RIFFdata")
        self.assertEqual(http.get("/api/redalert/audio/" + "x" * 30 + ".wav").status_code, 404)
        self.assertEqual(http.get("/api/redalert/audio/..%2Fetc.wav").status_code, 404)

    def test_alarm_triggers_and_clear_stops_but_widget_test_does_not(self):
        with mock.patch.object(service.redalert, "trigger") as trigger, mock.patch.object(service.redalert, "stop") as stop:
            desk_api._alert({"kind": "smoke", "room": "cucina", "title": "Fumo"})
            desk_api._alert({"kind": "smoke", "room": "cucina", "title": "Prova"}, red=False)
            desk_api._alert({"kind": "smoke", "room": "cucina", "clear": True})
        self.assertEqual(trigger.call_count, 1)
        self.assertIn("Fumo", trigger.call_args[0][0])
        stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
