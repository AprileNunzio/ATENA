import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

ROOT = Path(tempfile.mkdtemp(prefix="atena-vision-"))
os.environ["ATENA_FACES_DIR"] = str(ROOT / "faces")
os.environ["ATENA_VISION_MODELS"] = str(ROOT / "models")
os.environ["ATENA_WEBCAMS_FILE"] = str(ROOT / "webcams.json")
os.environ["ATENA_IR_STATUS"] = str(ROOT / "ir.json")
os.environ["ATENA_CAMERA"] = "/dev/null-camera"
for sub in ("faces", "models"):
    (ROOT / sub).mkdir()

VISION = Path(__file__).resolve().parents[1] / "features" / "vision"
if str(VISION) in sys.path:
    sys.path.remove(str(VISION))
sys.path.insert(0, str(VISION))

DIM = 128


def face_row(x, y, w, h):
    return [x, y, w, h, x + 0.3 * w, y + 0.4 * h, x + 0.7 * w, y + 0.4 * h, x + 0.5 * w, y + 0.6 * h,
            x + 0.35 * w, y + 0.8 * h, x + 0.65 * w, y + 0.8 * h, 0.99]


class FakeDetector:
    def __init__(self, *args, **kwargs):
        self.faces = []

    def setInputSize(self, size):
        self.size = size

    def detect(self, image):
        return 1, (np.array(self.faces, dtype=np.float32) if self.faces else None)


class FakeRecognizer:
    vec = np.ones(DIM, dtype=np.float32)

    def alignCrop(self, frame, face):
        return face

    def feature(self, crop):
        return self.vec.reshape(1, -1)


class FakeCv2Class:
    @staticmethod
    def create(*args, **kwargs):
        return FakeDetector()


class FakeRecogClass:
    @staticmethod
    def create(*args, **kwargs):
        return FakeRecognizer()


with mock.patch.object(cv2, "FaceDetectorYN", FakeCv2Class), mock.patch.object(cv2, "FaceRecognizerSF", FakeRecogClass):
    spec = importlib.util.spec_from_file_location("atena_vision_service", VISION / "service.py")
    service = importlib.util.module_from_spec(spec)
    sys.modules["atena_vision_service"] = service
    spec.loader.exec_module(service)
    import selection
    from tracks import Track

from features.biometrics import embeddings as emb


def vectors(seed, n=14, noise=0.05):
    rng = np.random.default_rng(seed)
    base = rng.standard_normal(DIM)
    return emb.unit_rows(base + rng.standard_normal((n, DIM)) * noise * np.abs(base).mean() * 4)


def ir_image(textured=True):
    rng = np.random.default_rng(1)
    gray = np.full((240, 320), 30, dtype=np.uint8)
    if textured:
        y, x = np.mgrid[0:70, 0:70]
        face = 120 * (1 + 0.5 * np.exp(-(((x - 35) ** 2 + (y - 35) ** 2) / 700))) + rng.standard_normal((70, 70)) * 35
        gray[80:150, 130:200] = np.clip(face, 0, 255).astype(np.uint8)
    return gray


class VisionServiceTest(unittest.TestCase):
    def setUp(self):
        self.vision, self.gallery = service.vision, service.gallery
        for slug in list(self.gallery.people):
            self.gallery.delete(slug)
        self.vision.tracks = []
        self.vision.det_size = (640, 480)
        Track._next = 1
        self.recognizer = self.vision.recognizer
        self.detector = self.vision.detector
        self.ir_detector = self.vision.fusion.detector
        self.detector.faces, self.ir_detector.faces = [], []
        self.vision.ir.gray = None
        self.env = mock.patch.dict(os.environ, {"ATENA_LIVENESS": "advisory", "ATENA_IR_MODE": "auto"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.photo = np.zeros((20, 20, 3), dtype=np.uint8)

    def enrol(self, slug, seed, ir=True, name=None):
        rgb = vectors(seed)
        self.gallery.save(name or slug.title(), list(rgb), self.photo, slug=slug, ir=list(vectors(seed + 100)) if ir else None)
        return rgb

    def frames(self, vec, count=5, box=(200, 120, 140, 160), ir=None, ir_faces=None, size=(480, 640), age=0.0):
        self.recognizer.vec = np.asarray(vec, dtype=np.float32)
        self.detector.faces = [face_row(*box)]
        frame = np.zeros((*size, 3), dtype=np.uint8)
        for _ in range(count):
            if ir is not None:
                self.vision.ir.gray, self.vision.ir.stamp = ir, time.time()
            self.ir_detector.faces = ir_faces if ir_faces is not None else []
            self.vision._process(frame.copy())
            for t in self.vision.tracks:
                t.first_seen -= age

    def person(self):
        people = self.vision.presence()["people"]
        return people[0] if people else None

    def test_known_person_with_real_infrared_face_is_live(self):
        rgb = self.enrol("anna", 1)
        self.frames(rgb[0], ir=ir_image(), ir_faces=[face_row(65, 45, 70, 70)])
        p = self.person()
        self.assertEqual((p["slug"], p["known"]), ("anna", True))
        self.assertEqual(p["liveness"]["state"], "live")
        self.assertFalse(p["ambiguous"])

    def test_face_visible_only_in_colour_is_flagged_but_advisory_keeps_the_identity(self):
        rgb = self.enrol("anna", 1)
        self.frames(rgb[0], ir=ir_image(False), ir_faces=[])
        p = self.person()
        self.assertEqual(p["liveness"]["state"], "spoof")
        self.assertEqual(p["slug"], "anna")

    def test_strict_mode_does_not_trust_a_spoof_and_learns_nothing(self):
        rgb = self.enrol("anna", 1)
        before = len(self.gallery.people["anna"]["embeddings"])
        with mock.patch.dict(os.environ, {"ATENA_LIVENESS": "strict"}):
            self.frames(rgb[0], count=8, ir=ir_image(False), ir_faces=[])
            p = self.person()
        self.assertEqual((p["known"], p["name"]), (False, "Foto o schermo"))
        self.assertEqual(len(self.gallery.people["anna"]["embeddings"]), before)

    def test_without_an_infrared_sensor_liveness_is_unknown_and_recognition_works(self):
        rgb = self.enrol("anna", 1, ir=False)
        self.frames(rgb[0])
        p = self.person()
        self.assertEqual((p["slug"], p["liveness"]["state"]), ("anna", "unknown"))

    def test_liveness_can_be_switched_off(self):
        rgb = self.enrol("anna", 1)
        with mock.patch.dict(os.environ, {"ATENA_LIVENESS": "off"}):
            self.frames(rgb[0], ir=ir_image(False), ir_faces=[])
            self.assertEqual(self.person()["liveness"]["state"], "unknown")

    def test_look_alikes_are_left_ambiguous_and_never_merged_or_enrolled(self):
        anna = self.enrol("anna", 1, ir=False)
        twin = vectors(2, 14, 0.05)
        twin = emb.unit_rows(emb.centroid(anna) * 0.97 + twin * 0.03)
        self.gallery.save("Alba", list(twin), self.photo, slug="alba")
        self.assertTrue(self.gallery.twins)
        probe = emb.unit(emb.centroid(anna) + emb.centroid(twin))
        self.frames(probe, count=14, age=3.0)
        people = self.gallery.people
        self.assertEqual(set(people), {"anna", "alba"})
        p = self.person()
        self.assertTrue(p is None or not p["known"] or p["slug"] in ("anna", "alba"))
        if p and not p["known"]:
            self.assertTrue(p["ambiguous"])
            self.assertEqual(set(p["possible"]), {"Anna", "Alba"})
        self.assertEqual(len(people["anna"]["embeddings"]), 14)

    def test_each_twin_is_still_recognised_with_a_clear_view(self):
        anna = self.enrol("anna", 1, ir=False)
        twin = emb.unit_rows(emb.centroid(anna) * 0.6 + vectors(2, 14, 0.05) * 0.4)
        self.gallery.save("Alba", list(twin), self.photo, slug="alba")
        self.frames(twin[3], count=8, age=3.0)
        self.assertEqual(self.person()["slug"], "alba")
        self.vision.tracks = []
        self.frames(anna[3], count=8, age=3.0)
        self.assertEqual(self.person()["slug"], "anna")

    def test_new_person_is_enrolled_with_infrared_samples_and_a_far_stranger_is_not_merged(self):
        self.enrol("anna", 1, ir=False)
        stranger = vectors(50, 1)[0]
        self.frames(stranger, count=36, age=3.0, ir=ir_image(), ir_faces=[face_row(65, 45, 70, 70)])
        guests = [s for s in self.gallery.people if s.startswith("ospite-")]
        self.assertEqual(len(guests), 1)
        self.assertGreater(self.gallery.people[guests[0]]["ir"].shape[0], 0)
        self.assertEqual(len(self.gallery.people["anna"]["embeddings"]), 14)

    def test_known_person_keeps_improving_with_diverse_samples_up_to_the_limit(self):
        rgb = self.enrol("anna", 1, ir=False)
        rng = np.random.default_rng(9)
        for i in range(60):
            probe = emb.unit(rgb[i % 14] + rng.standard_normal(DIM) * 0.03)
            self.vision.tracks = []
            self.recognizer.vec = probe
            self.detector.faces = [face_row(200, 120, 140, 160)]
            self.vision._process(np.zeros((480, 640, 3), dtype=np.uint8))
            for t in self.vision.tracks:
                t.last_learn = 0.0
        count = len(self.gallery.people["anna"]["embeddings"])
        self.assertGreater(count, 14)
        self.assertLessEqual(count, service.Gallery.__init__.__globals__["MAX_SAMPLES"])

    def test_high_resolution_frames_are_detected_downscaled_but_boxes_are_full_size(self):
        rgb = self.enrol("anna", 1, ir=False)
        self.recognizer.vec = rgb[0]
        self.detector.faces = [face_row(100, 60, 70, 80)]
        self.vision._process(np.zeros((720, 1280, 3), dtype=np.uint8))
        self.assertEqual(self.vision.size, (1280, 720))
        self.assertEqual(self.vision.det_size, (640, 360))
        self.assertEqual(self.vision.tracks[0].box, (200, 120, 140, 160))

    def test_health_and_ir_endpoints_expose_the_new_state(self):
        from fastapi.testclient import TestClient
        client = TestClient(service.app)
        health = client.get("/health").json()
        for key in ("camera", "ir", "liveness", "similar_pairs"):
            self.assertIn(key, health)
        self.enrol("anna", 1)
        listing = client.get("/people/health").json()["people"]
        self.assertEqual(listing[0]["slug"], "anna")
        self.assertEqual(listing[0]["samples_ir"], 14)
        self.assertEqual(client.get("/ir.jpg").status_code, 503)
        self.vision.ir.gray, self.vision.ir.stamp = ir_image(), time.time()
        self.assertEqual(client.get("/ir.jpg").headers["content-type"], "image/jpeg")

    def test_enrolment_collects_infrared_samples_too(self):
        self.recognizer.vec = vectors(60, 1)[0]
        self.detector.faces = [face_row(200, 120, 140, 160)]
        self.vision.ir.gray, self.vision.ir.stamp = ir_image(), time.time()
        self.ir_detector.faces = [face_row(65, 45, 70, 70)]
        self.vision.enroll_request = {"samples": [], "photo": None}
        for _ in range(6):
            self.vision.ir.stamp = time.time()
            self.vision._process(np.zeros((480, 640, 3), dtype=np.uint8))
        request, self.vision.enroll_request = self.vision.enroll_request, None
        self.assertEqual(len(request["samples"]), 6)
        self.assertEqual(len(request["ir"]), 6)
        person = self.gallery.save("Nuovo", request["samples"], request["photo"], ir=request["ir"])
        self.assertEqual(person["samples_ir"], 6)

    def test_camera_selection_defaults_and_overrides(self):
        self.assertEqual(selection.current()["rgb"], "/dev/null-camera")
        self.assertEqual(selection.capture_size(None, 8), (1280, 720))
        self.assertEqual(selection.capture_size(None, 2), (640, 480))
        self.assertEqual(selection.capture_size({"width": 640, "height": 480}, 8), (640, 480))
        with mock.patch.dict(os.environ, {"ATENA_CAMERA_RES": "1920x1080"}):
            self.assertEqual(selection.capture_size({"width": 1920, "height": 1080}, 2), (1920, 1080))
        with mock.patch.dict(os.environ, {"ATENA_IR_MODE": "off"}):
            self.assertFalse(selection.ir_enabled())
        with mock.patch.dict(os.environ, {"ATENA_LIVENESS": "boh", "ATENA_LIVENESS_MIN": "9"}):
            self.assertEqual(selection.liveness_mode(), "advisory")
            self.assertEqual(selection.liveness_minimum(), 0.95)


if __name__ == "__main__":
    unittest.main()
