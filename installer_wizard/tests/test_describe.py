import asyncio
import time
import unittest
from unittest import mock

from features.brain.llm import BrainUnavailable
from features.cameras import live
from features.cameras.cameras import cameras
from features.desktop.desk import desk
from features.vision import describe, sight
from features.vision.webcams import webcams
from state import store

JPEG = b"\xff\xd8\xff\xe0fake"
ANN = {"name": "Ann", "known": True, "near": True, "facing": True, "since": time.time() - 400, "liveness": {"state": "live"}}
STRANGER = {"name": "Sconosciuto", "known": False, "near": False, "facing": False, "since": time.time() - 10, "liveness": {"state": "live"}}


def device(name: str, node: str, bus: str) -> dict:
    return {"id": f"0c45:6366@{bus}", "name": name, "rgb": node, "ir": None, "has_ir": False}


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = (webcams.state, dict(cameras.items), dict(desk.instances), store.presence)
        self.addCleanup(self.restore)
        desk.scan()
        desk.instances.clear()
        cameras.items = {}
        webcams.state = {"devices": [device("HD Webcam", "/dev/video0", "usb-1")], "selected": {"rgb": "/dev/video0"}, "problems": []}
        store.presence = {"status": "ok", "people": [ANN, STRANGER], "summary": "",
                          "objects": [{"label": "tazza", "held": True, "scenery": False, "box": [10, 10, 40, 40]},
                                      {"label": "laptop", "held": False, "scenery": False, "box": [100, 100, 80, 60]}]}

    def restore(self):
        webcams.state, cameras.items, desk.instances, store.presence = self.saved

    def ask(self, text: str = "cosa vedi", llm=None, jpeg=JPEG):
        async def fake_look(*args, **kwargs):
            if llm is None:
                raise BrainUnavailable("nessun modello")
            return llm, "modello-prova"

        with mock.patch.object(live, "snapshot_bytes", mock.AsyncMock(return_value=jpeg)), \
                mock.patch.object(describe.seeing, "look", fake_look), \
                mock.patch.object(describe, "brightness", return_value=120.0):
            return asyncio.run(sight.answer(text))


class DescribeTest(Base):
    def test_without_a_vision_model_it_still_lists_people_objects_and_hints_at_the_upgrade(self):
        speech, ui = self.ask()
        self.assertIn("Vedo 2 persone", speech)
        self.assertIn("Ann, vicino", speech)
        self.assertIn("una persona che non conosco, lontano", speech)
        self.assertIn("In mano ha tazza", speech)
        self.assertIn("laptop", speech)
        self.assertIn("modello che vede", speech)
        self.assertEqual(ui["mode"], "focus")
        self.assertEqual({p["type"] for p in ui["panels"]}, {"annotated", "list"})

    def test_with_a_vision_model_the_scene_description_is_added_and_boxes_are_kept(self):
        data = {"description": "Una stanza luminosa con un divano blu.", "text": "OPEN",
                "objects": [{"label": "divano", "box": [0.1, 0.5, 0.4, 0.3]}, {"label": "rotto", "box": [5, 5, 5, 5]}]}
        speech, ui = self.ask(llm=data)
        self.assertIn("Una stanza luminosa con un divano blu.", speech)
        self.assertIn("C'è scritto: OPEN", speech)
        self.assertNotIn("modello che vede", speech)
        annotated = next(p for p in ui["panels"] if p["type"] == "annotated")
        self.assertEqual([b["label"] for b in annotated["boxes"]], ["divano"])

    def test_empty_room_and_dark_images(self):
        store.presence = {"status": "ok", "people": [], "summary": "", "objects": []}
        with mock.patch.object(describe, "brightness", return_value=10.0):
            async def run():
                with mock.patch.object(live, "snapshot_bytes", mock.AsyncMock(return_value=JPEG)), \
                        mock.patch.object(describe.seeing, "look", mock.AsyncMock(side_effect=BrainUnavailable("no"))):
                    return await describe.answer("cosa vedi")
            speech, _ = asyncio.run(run())
        self.assertIn("Non vedo nessuna persona", speech)
        self.assertIn("molto buia", speech)

    def test_spoofed_faces_are_not_called_people(self):
        store.presence = {"status": "ok", "people": [{**STRANGER, "liveness": {"state": "spoof"}}], "summary": "", "objects": []}
        speech, _ = self.ask()
        self.assertIn("una foto o uno schermo", speech)

    def test_no_camera_no_picture_and_no_webcam_connected(self):
        speech, _ = self.ask(jpeg=None)
        self.assertIn("non riesco a ottenere l'immagine", speech)
        webcams.state = {"devices": [], "selected": {}, "problems": []}
        speech, ui = self.ask()
        self.assertIn("nessuna webcam", speech)
        self.assertEqual(ui["mode"], "face")

    def test_with_a_live_widget_open_it_only_speaks_and_does_not_cover_the_screen(self):
        row = live.listing()[0]
        desk.show("live_cam", {"source": row["id"], "name": row["name"]}, key=f"live:{row['id']}")
        speech, ui = self.ask()
        self.assertIn("Vedo 2 persone", speech)
        self.assertEqual(ui["mode"], "face")

    def test_a_named_camera_is_described_on_its_own_and_others_need_the_model(self):
        webcams.state = {"devices": [device("HD Webcam", "/dev/video0", "usb-1"), device("Camera Studio", "/dev/video2", "usb-2")],
                         "selected": {"rgb": "/dev/video0"}, "problems": []}
        speech, _ = self.ask("cosa vede la telecamera studio")
        self.assertNotIn("Ann", speech)
        self.assertIn("non ha un riconoscimento locale", speech)
        speech, _ = self.ask("cosa vedi")
        self.assertIn("Ann", speech)

    def test_phrases_that_trigger_the_description(self):
        for text in ("cosa vedi", "cosa vede la webcam", "che cosa vedi adesso", "cosa succede nella stanza", "cosa stai vedendo"):
            self.assertTrue(sight.SCENE.search(text), text)
        self.assertFalse(sight.SCENE.search("che tempo fa"))

    def test_helpers(self):
        self.assertEqual(describe.join(["a"]), "a")
        self.assertEqual(describe.join(["a", "b", "c"]), "a, b e c")
        self.assertEqual(describe.since(time.time() - 10), "da poco")
        self.assertEqual(describe.since(time.time() - 600), "da 10 minuti")
        self.assertEqual(describe.since(time.time() - 7300), "da 2 ore")


if __name__ == "__main__":
    unittest.main()
