import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from fastapi import HTTPException, Response

from features.people import faces, people
from features.vision import gallery as gallery_module


def unit(seed: int, count: int) -> np.ndarray:
    rows = np.random.default_rng(seed).standard_normal((count, 128)).astype(np.float32)
    return rows / np.linalg.norm(rows, axis=1, keepdims=True)


def face(root: Path, slug: str, name: str, samples: int = 0, auto: bool = False, ir: int = 0) -> Path:
    folder = root / slug
    (folder / "photos").mkdir(parents=True)
    meta = {"name": name, "auto": auto, "samples": samples}
    if samples:
        np.save(folder / "embeddings.npy", unit(len(slug) + samples, samples))
    if ir:
        np.save(folder / "embeddings_ir.npy", unit(len(slug) + 99, ir))
        meta["samples_ir"] = ir
    (folder / "photo.jpg").write_bytes(b"jpeg")
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


class FacesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.faces, self.people_dir = root / "faces", root / "people"
        self.faces.mkdir()
        self.patches = [mock.patch.object(people, "PEOPLE_DIR", self.people_dir),
                        mock.patch.object(gallery_module, "FACES", self.faces)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_a_guest_seen_only_by_the_camera_appears_in_people(self):
        face(self.faces, "ospite-1728000000", "Ospite 1", samples=6, auto=True)
        self.assertEqual(faces.sync_gallery(self.faces), ["ospite-1728000000"])
        profile = people.load("ospite-1728000000")
        self.assertEqual(profile["name"], "Ospite 1")
        self.assertTrue(profile["auto"])
        self.assertEqual(faces.sync_gallery(self.faces), [])

    def test_quality_is_zero_without_face_samples(self):
        face(self.faces, "nunzio", "Nunzio")
        self.assertEqual(faces.quality(self.faces, "nunzio"), 0)
        self.assertEqual(faces.quality(self.faces, "nessuno"), 0)
        face(self.faces, "anna", "Anna", samples=12)
        self.assertGreater(faces.quality(self.faces, "anna"), 0)

    def test_merging_into_a_person_without_samples_keeps_every_sample(self):
        face(self.faces, "nunzio", "Nunzio")
        face(self.faces, "ospite-1", "Ospite 1", samples=8, auto=True, ir=3)
        gallery = gallery_module.Gallery()
        merged = gallery.merge("ospite-1", "nunzio", "Nunzio")
        self.assertEqual((merged["samples"], merged["samples_ir"]), (8, 3))
        self.assertEqual(len(np.load(self.faces / "nunzio" / "embeddings.npy")), 8)
        self.assertFalse((self.faces / "ospite-1").exists())
        self.assertTrue(any((self.faces / "nunzio" / "photos").glob("merged_ospite-1_*.jpg")))
        self.assertIn("nunzio", gallery.people)
        self.assertEqual(gallery.people["nunzio"]["name"], "Nunzio")

    def test_merging_keeps_samples_of_both_faces(self):
        face(self.faces, "nunzio", "Nunzio", samples=10)
        face(self.faces, "ospite-1", "Ospite 1", samples=10, auto=True)
        merged = gallery_module.Gallery().merge("ospite-1", "nunzio", "Nunzio")
        self.assertGreater(merged["samples"], 10)


class AssociateTest(FacesTest):
    def seed_profiles(self):
        people.ensure("nunzio", "Nunzio")
        guest = people.ensure("ospite-1", "Ospite 1")
        guest["stats"] = {"visits": 3, "total_seconds": 60}
        people.save(guest)

    def test_a_vision_failure_never_loses_the_guest(self):
        self.seed_profiles()
        down = Response(json.dumps({"detail": "Servizio di visione non disponibile"}).encode(), status_code=503)
        with mock.patch("features.people.faces.vision_proxy", new_callable=mock.AsyncMock, return_value=down):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(faces.associate("ospite-1", "nunzio"))
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIsNotNone(people.load("ospite-1"))

    def test_association_moves_visits_and_removes_the_guest(self):
        self.seed_profiles()
        ok = Response(b"{}", status_code=200)
        with mock.patch("features.people.faces.vision_proxy", new_callable=mock.AsyncMock, return_value=ok) as proxy:
            target = asyncio.run(faces.associate("ospite-1", "nunzio"))
        proxy.assert_awaited_once()
        self.assertEqual(proxy.await_args.args[2], {"into": "nunzio", "name": "Nunzio"})
        self.assertEqual(target["stats"]["visits"], 3)
        self.assertIsNone(people.load("ospite-1"))


if __name__ == "__main__":
    unittest.main()
