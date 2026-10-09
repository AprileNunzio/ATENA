import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.authz.heard import HeardLog
from features.home_assistant.nlu.matching import Catalog, area_names
from features.home_assistant.nlu.parser import parse_command
from features.places import commands, context
from features.places import store as store_module
from features.places.locate import Locator, current_room, locator
from features.places.store import store


class PlacesBase(unittest.TestCase):

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(store_module, "PLACES_FILE", Path(folder.name) / "places.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        store.floors, store.rooms, store.placements = {}, {}, {}
        locator.clues.clear()
        self.ground = store.put_floor({"name": "Piano terra", "level": 0})
        self.first = store.put_floor({"name": "Primo piano", "level": 1})
        self.studio = store.put_room({"name": "Studio", "floor_id": self.first.id, "ha_area": "studio"})
        self.kitchen = store.put_room({"name": "Cucina", "floor_id": self.ground.id, "ha_area": "cucina"})
        store.place("node:studio-pc", self.studio.id, ["hears", "speaks"])
        store.place("camera:main", self.kitchen.id, ["sees"])
        store.place("display:kiosk", self.kitchen.id, ["shows"])
        self.addCleanup(lambda: current_room.set(None))


class StoreTests(PlacesBase):

    def test_map_survives_a_restart(self):
        store.floors, store.rooms, store.placements = {}, {}, {}
        store.load()
        self.assertEqual(store.room_of("node:studio-pc").name, "Studio")
        self.assertEqual(store.rooms[self.studio.id].floor_id, self.first.id)

    def test_validation(self):
        with self.assertRaises(ValueError):
            store.put_room({"name": "studio"})
        with self.assertRaises(ValueError):
            store.place("node:../../etc", self.studio.id, [])
        with self.assertRaises(ValueError):
            store.place("camera:main", "nessuna", [])
        with self.assertRaises(ValueError):
            store.put_room({"name": "<script>"})

    def test_deleting_a_room_unplaces_its_devices_and_floor_deletion_keeps_rooms(self):
        store.delete_room(self.studio.id)
        self.assertIsNone(store.room_of("node:studio-pc"))
        store.delete_floor(self.ground.id)
        self.assertEqual(store.rooms[self.kitchen.id].floor_id, "")

    def test_home_assistant_areas_are_imported_once(self):
        floors = {"f1": {"name": "Seminterrato", "level": -1}}
        areas = {"cantina": {"name": "Cantina", "floor_id": "f1"}, "cucina": {"name": "Cucina"}}
        self.assertEqual(store.import_areas(floors, areas), 1)
        self.assertEqual(store.import_areas(floors, areas), 0)
        cantina = next(r for r in store.rooms.values() if r.name == "Cantina")
        self.assertEqual(store.floors[cantina.floor_id].level, -1)


class LocatorTests(PlacesBase):

    def test_recent_voice_beats_an_older_face(self):
        loc = Locator()
        loc.note("nunzio", "face", "camera:main", 0.9, at=1000)
        loc.note("nunzio", "voice", "node:studio-pc", 0.8, at=1060)
        self.assertEqual(loc.room("nunzio", now=1061).name, "Studio")

    def test_clues_fade_and_unplaced_devices_are_ignored(self):
        loc = Locator()
        loc.note("anna", "voice", "node:studio-pc", 1.0, at=1000)
        loc.note("anna", "voice", "node:sconosciuto", 1.0, at=1000)
        self.assertIsNone(loc.room("anna", now=1000 + 600))

    def test_the_device_used_is_the_fallback(self):
        self.assertEqual(context.enter("", "", "kiosk").name, "Cucina")
        self.assertEqual(context.enter("", "", "studio-pc").name, "Studio")
        self.assertEqual(context.area(), "studio")
        self.assertIsNone(context.enter("", "", "admin"))

    def test_hearing_on_a_satellite_places_the_speaker(self):
        log = HeardLog()
        log.tap(json.dumps({"type": "transcript", "text": "accendi la luce", "speaker": "nunzio", "speaker_score": 0.8}),
                "node:studio-pc")
        self.assertEqual(log.verify("nunzio", "accendi la luce").device, "node:studio-pc")
        self.assertEqual(context.enter("nunzio", "node:studio-pc", "kiosk").name, "Studio")


class HomeCommandTests(PlacesBase):

    def catalog(self) -> Catalog:
        cat = Catalog()
        names = ["Studio", "Cucina"]
        for aid, name in (("studio", "Studio"), ("cucina", "Cucina")):
            cat.areas[aid] = {"name": name, "floor_id": None, "names": area_names(name, [], names)}
            cat.entities[f"light.{aid}"] = {"entity_id": f"light.{aid}", "domain": "light", "name": f"Luce {name}",
                                            "area_id": aid, "device_id": aid, "controllable": True, "names": [],
                                            "caps": set(), "state": "off", "attrs": {}, "is_group": False, "as_light": False}
        cat.default_area = "cucina"
        return cat

    def test_turn_on_the_light_uses_the_room_you_are_in(self):
        context.enter("nunzio", "node:studio-pc", "studio-pc")
        result = parse_command("accendi la luce", self.catalog())
        self.assertEqual(result["entities"], ["light.studio"])
        self.assertEqual(result["how"], "stanza in cui sei")

    def test_a_named_room_still_wins(self):
        context.enter("nunzio", "node:studio-pc", "studio-pc")
        self.assertEqual(parse_command("accendi la luce in cucina", self.catalog())["entities"], ["light.cucina"])

    def test_rooms_link_to_home_assistant_areas_by_name(self):
        from features.home_assistant.home import brain
        room = store.put_room({"name": "Camera da letto", "floor_id": self.first.id})
        current_room.set(room)
        with mock.patch.object(brain, "areas", {"camera": {"name": "camera da letto"}}, create=True):
            self.assertEqual(context.area(), "camera")

    def test_without_location_atena_room_is_used(self):
        current_room.set(None)
        self.assertEqual(parse_command("accendi la luce", self.catalog())["entities"], ["light.cucina"])


class WhereAmITests(PlacesBase):

    def test_answers_with_room_and_floor(self):
        context.enter("", "", "studio-pc")
        speech, _ = asyncio.run(commands.answer("in che stanza sono?"))
        self.assertIn("Studio, al primo piano", speech)
        with self.assertRaises(LookupError):
            asyncio.run(commands.answer("che ore sono"))


if __name__ == "__main__":
    unittest.main()
