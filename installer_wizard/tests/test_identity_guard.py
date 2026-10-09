import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from state import store

from features.chat.skills import people as people_skill
from features.people import faces, people


class IdentityGuardTests(unittest.TestCase):

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(people, "PEOPLE_DIR", Path(folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        owner = people.ensure("nunzio-aprile", "Nunzio Aprile")
        owner.update(first_name="Nunzio", last_name="Aprile", role="owner")
        people.save(owner)
        guest = people.ensure("ospite-1", "Ospite 1")
        guest["auto"] = True
        people.save(guest)
        self.saved = store.presence
        store.presence = {"people": [{"slug": "ospite-1", "name": "Ospite 1", "known": True, "auto": True}]}
        self.addCleanup(lambda: setattr(store, "presence", self.saved))

    def test_a_stranger_cannot_take_the_owner_name_by_voice(self):
        with mock.patch.object(people_skill.httpx, "AsyncClient") as client:
            reply, _ = asyncio.run(people_skill.introduce_skill("mi chiamo Nunzio"))
        client.assert_not_called()
        self.assertIn("Conosco già", reply)
        self.assertEqual(people.load("ospite-1")["role"], "guest")
        self.assertEqual(people.display_name(people.load("ospite-1")), "Ospite 1")

    def test_a_new_name_is_still_accepted(self):
        response = mock.MagicMock()
        response.raise_for_status.return_value = None
        session = mock.AsyncMock()
        session.patch.return_value = response
        with mock.patch.object(people_skill.httpx, "AsyncClient") as client:
            client.return_value.__aenter__.return_value = session
            reply, _ = asyncio.run(people_skill.introduce_skill("mi chiamo Marco Rossi"))
        self.assertIn("Marco Rossi", reply)

    def test_the_owner_profile_is_never_deleted_by_an_association(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(faces.associate("nunzio-aprile", "ospite-1"))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIsNotNone(people.load("nunzio-aprile"))


if __name__ == "__main__":
    unittest.main()
