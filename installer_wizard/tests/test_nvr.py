import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from atena_bus import AtenaBus

from features.nvr import service as nvr_service
from features.nvr import settings as nvr_settings
from features.nvr.ingest import parse_event
from features.nvr.search import parse
from features.nvr.store import EventStore

NOW = datetime(2025, 10, 6, 15, 0).timestamp()


def event(**kw):
    base = {"id": "e1", "at": NOW - 60, "camera": "Giardino", "label": "person", "score": 0.9, "source": "mqtt", "zone": "vialetto", "text": ""}
    base.update(kw)
    return base


class SearchParseTest(unittest.TestCase):
    def test_labels_synonyms_time_and_terms(self):
        q = parse("trovami la macchina rossa ieri in giardino", NOW)
        self.assertEqual(q.labels, frozenset({"car"}))
        self.assertIn("giardino", q.terms)
        self.assertIn("rossa", q.terms)
        self.assertEqual(datetime.fromtimestamp(q.until).hour, 0)
        self.assertEqual(parse("animali oggi", NOW).labels, frozenset({"dog", "cat", "bird"}))
        self.assertAlmostEqual(parse("persona ultima ora", NOW).since, NOW - 3600)

    def test_hostile_input_is_bounded(self):
        q = parse("%_' OR 1=1 --" * 100, NOW)
        self.assertLessEqual(len(q.terms), 6)


class StoreTest(unittest.TestCase):
    def test_search_filters_and_escapes_wildcards(self):
        with tempfile.TemporaryDirectory() as root:
            store = EventStore(Path(root) / "e.db")
            self.addCleanup(store.close)
            self.assertTrue(store.add(event()))
            self.assertFalse(store.add(event()))
            store.add(event(id="e2", label="car", camera="Ingresso", zone=""))
            store.add(event(id="e3", camera="100%_garage", label="dog"))
            self.assertEqual([e["id"] for e in store.search(parse("persona giardino", NOW))], ["e1"])
            self.assertEqual([e["id"] for e in store.search(parse("auto", NOW))], ["e2"])
            wild = parse("", NOW)
            self.assertEqual([e["id"] for e in store.search(type(wild)(wild.since, wild.until, frozenset(), ("%",)))], ["e3"])
            self.assertEqual([e["id"] for e in store.search(type(wild)(wild.since, wild.until, frozenset(), ("_g",)))], ["e3"])
            self.assertEqual(store.counts(NOW - 3600), {"person": 1, "car": 1, "dog": 1})
            self.assertEqual(store.prune(0), 3)


class IngestTest(unittest.TestCase):
    def test_parses_common_after_schema(self):
        raw = json.dumps({"type": "new", "after": {"id": "abc", "camera": "giardino", "label": "Person", "top_score": 0.87,
                                                    "start_time": NOW, "current_zones": ["prato"]}}).encode()
        e = parse_event(raw)
        self.assertEqual((e["id"], e["label"], e["zone"], e["score"]), ("mqtt:abc", "person", "prato", 0.87))

    def test_rejects_garbage(self):
        for raw in (b"\xff", b"[]", b"{}", json.dumps({"after": {"camera": "x"}}).encode(), b"{" * 70000,
                    json.dumps({"type": "drop", "after": {"camera": "c", "label": "l"}}).encode()):
            self.assertIsNone(parse_event(raw))


class SettingsTest(unittest.TestCase):
    def test_password_is_write_only_and_validation(self):
        current = dict(nvr_settings.DEFAULTS)
        fresh = nvr_settings.validate({"enabled": True, "mqtt_host": "192.168.1.20", "mqtt_password": "s3cret", "labels": ["person", "evil"]}, current)
        self.assertEqual(fresh["labels"], ["person"])
        shown = nvr_settings.public(fresh)
        self.assertNotIn("mqtt_password", shown)
        self.assertTrue(shown["has_password"])
        self.assertEqual(nvr_settings.validate({"mqtt_password": ""}, fresh)["mqtt_password"], "s3cret")
        self.assertEqual(nvr_settings.validate({"clear_password": True}, fresh)["mqtt_password"], "")
        for bad in ({"enabled": True, "mqtt_host": ""}, {"mqtt_host": "bad host;rm"}, {"mqtt_port": 0}, {"mqtt_topic": "a b"}, {"labels": "person"}):
            with self.assertRaises(nvr_settings.SettingsError):
                nvr_settings.validate(bad, current)

    def test_settings_file_is_private(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(nvr_settings, "NVR_DIR", Path(root)), \
                mock.patch.object(nvr_settings, "SETTINGS_FILE", Path(root) / "s.json"):
            nvr_settings.save({"mqtt_password": "x"})
            self.assertEqual((Path(root) / "s.json").stat().st_mode & 0o777, 0o600)


class ServiceTest(unittest.TestCase):
    def test_events_are_filtered_stored_and_published(self):
        with tempfile.TemporaryDirectory() as root:
            bus = AtenaBus()
            got = []
            bus.subscribe("nvr.>", got.append)
            with mock.patch.object(nvr_service, "atena_bus", bus):
                nvr = nvr_service.Nvr()
                nvr._store = EventStore(Path(root) / "e.db")
                self.addCleanup(nvr._store.close)
                nvr.settings = {**nvr_settings.DEFAULTS, "labels": ["person", "motion"], "notify_labels": ["person"], "min_score": 0.6}
                self.assertTrue(nvr.record(event()))
                self.assertFalse(nvr.record(event(id="low", score=0.3)))
                self.assertFalse(nvr.record(event(id="cat", label="cat")))
                env = type("E", (), {"payload": {"at": NOW, "kind": "motion", "source": "c-1", "name": "Ingresso", "text": "Movimento"}, "ts": NOW})()
                nvr.on_camera_event(env)
            self.assertEqual([e.topic for e in got], ["nvr.event.giardino", "nvr.alert", "nvr.event.ingresso"])


if __name__ == "__main__":
    unittest.main()
