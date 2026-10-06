import json
import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from config import WIDGETS_DIR
from features.desktop import sources
from features.desktop.desk import TONES, Desk
from state import store

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


class ManifestTest(unittest.TestCase):
    def test_every_widget_declares_a_valid_look(self):
        for path in sorted(WIDGETS_DIR.glob("*/widget.json")):
            with self.subTest(widget=path.parent.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn(data.get("tone", "cyan"), TONES)
                self.assertIsInstance(data.get("essential", False), bool)
                script = (path.parent / "widget.js").read_text(encoding="utf-8")
                self.assertNotIn("jarvis", script.lower())
                self.assertNotIn("#0f172a", script)

    def test_widget_scripts_use_vector_icons_not_emoji(self):
        offenders = [p.parent.name for p in WIDGETS_DIR.glob("*/widget.js") if EMOJI.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])

    def test_desk_publishes_tone_and_essential(self):
        desk = Desk()
        desk.scan()
        desk.show("cyber_alert", {"source_ip": "10.0.0.1"})
        desk.show("weather", {})
        active = {i["id"]: i for i in desk.active()}
        self.assertTrue(active["cyber_alert"]["essential"])
        self.assertEqual(active["cyber_alert"]["tone"], "red")
        self.assertFalse(active["weather"]["essential"])


class SourcesTest(unittest.TestCase):
    def test_sun_cycle_reports_today(self):
        now = datetime.now().astimezone().replace(hour=12, minute=0)
        fake = {"sunrise": now - timedelta(hours=5), "sunset": now + timedelta(hours=5)}
        with mock.patch("features.automations.sun.times", return_value=fake):
            data = sources.sun_cycle()
        self.assertEqual(data["daylight_min"], 600)
        self.assertTrue(0 <= data["progress"] <= 100)
        with mock.patch("features.automations.sun.times", return_value={"sunrise": None, "sunset": None}):
            self.assertIsNone(sources.sun_cycle())

    def test_alerts_only_when_ready(self):
        phase, comps, upd = store.phase, store.components, store.update
        try:
            store.components = {"voice": {"label": "Voce", "status": "down", "detail": "<b>x</b>"}, "core": {"label": "Core", "status": "ok"}}
            store.update = {"available": True, "local_rev": "aaaaaaaaaaaa", "remote_rev": "bbbbbbbbbbbb", "changelog": ["x"] * 20}
            store.phase = "INSTALLING"
            self.assertIsNone(sources.components_down())
            self.assertIsNone(sources.update_ready())
            store.phase = "READY"
            self.assertEqual([i["label"] for i in sources.components_down()["items"]], ["Voce"])
            up = sources.update_ready()
            self.assertEqual(len(up["changes"]), 6)
            self.assertEqual(up["remote"], "bbbbbbbbbb")
            store.components = {"core": {"label": "Core", "status": "ok"}}
            self.assertIsNone(sources.components_down())
        finally:
            store.phase, store.components, store.update = phase, comps, upd

    def test_a_broken_source_does_not_stop_the_others(self):
        desk = Desk()
        desk.scan()
        desk.register_source("update_ready", lambda: 1 / 0)
        desk.register_source("components_down", lambda: {"items": [{"label": "Voce", "detail": "", "status": "down"}]})
        desk._bindings()
        self.assertIn("bind:subsystem_alert", desk.instances)
        self.assertNotIn("bind:system_update", desk.instances)


if __name__ == "__main__":
    unittest.main()
