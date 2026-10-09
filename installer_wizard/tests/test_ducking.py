import asyncio
import time
import unittest
from unittest import mock

from features.ducking import ducker as ducker_module
from features.ducking import targets
from features.ducking.ducker import RELEASE_AFTER, Ducker


class FakeTarget(targets.Target):
    kind = "fake"

    def __init__(self, ident: str, original: float, fail: bool = False) -> None:
        super().__init__(ident, ident, original)
        self.volume, self.fail = original, fail

    async def set(self, value: float) -> None:
        if self.fail:
            raise RuntimeError("non risponde")
        self.volume = value

    async def current(self) -> float | None:
        return self.volume


class DuckerTest(unittest.TestCase):
    def setUp(self):
        self.speaker, self.tv, self.broken = FakeTarget("casse", 0.8), FakeTarget("tv", 0.5), FakeTarget("rotto", 0.6, True)
        self.ducker = Ducker()
        found = [self.speaker, self.tv, self.broken]
        self.patches = [mock.patch.object(Ducker, "collect", mock.AsyncMock(return_value=found)),
                        mock.patch.object(ducker_module, "env_get", side_effect=lambda k, d="": {"ATENA_DUCK_LEVEL": "25"}.get(k, d))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_duck_and_restore(self):
        asyncio.run(self.ducker.signal(True))
        self.assertEqual((self.speaker.volume, self.tv.volume), (0.2, 0.12))
        self.assertEqual([t.name for t in self.ducker.ducked], ["casse", "tv"])
        asyncio.run(self.ducker.signal(False))
        asyncio.run(self.ducker.tick())
        self.assertEqual(self.speaker.volume, 0.2)
        self.ducker.off_at = time.time() - RELEASE_AFTER - 1
        asyncio.run(self.ducker.tick())
        self.assertEqual((self.speaker.volume, self.tv.volume), (0.8, 0.5))
        self.assertFalse(self.ducker.active)

    def test_volume_changed_by_hand_is_left_alone(self):
        asyncio.run(self.ducker.signal(True))
        self.tv.volume = 0.9
        asyncio.run(self.ducker.release())
        self.assertEqual(self.tv.volume, 0.9)
        self.assertEqual(self.speaker.volume, 0.8)

    def test_turns_between_replies_do_not_restore_and_lost_display_does(self):
        asyncio.run(self.ducker.signal(True))
        asyncio.run(self.ducker.signal(False))
        asyncio.run(self.ducker.signal(True))
        self.ducker.off_at = 0.0
        asyncio.run(self.ducker.tick())
        self.assertTrue(self.ducker.active)
        self.ducker.beat = time.time() - 60
        asyncio.run(self.ducker.tick())
        self.assertEqual(self.speaker.volume, 0.8)

    def test_disabled_does_nothing(self):
        with mock.patch.object(ducker_module, "env_get", side_effect=lambda k, d="": "0" if k == "ATENA_DUCKING" else d):
            asyncio.run(self.ducker.signal(True))
        self.assertFalse(self.ducker.active)
        self.assertEqual(self.speaker.volume, 0.8)


class HomeTargetTest(unittest.TestCase):
    def test_only_playing_media_players_with_volume(self):
        from features.home_assistant.home import brain
        states = {"media_player.salotto": {"state": "playing", "attrs": {"volume_level": 0.6, "friendly_name": "Salotto"}},
                  "media_player.cucina": {"state": "paused", "attrs": {"volume_level": 0.4}},
                  "light.sala": {"state": "on", "attrs": {}}}
        with mock.patch.object(brain, "states", states), mock.patch.object(brain, "status", "online"):
            found = targets.home()
        self.assertEqual([(t.ident, t.name, t.original) for t in found], [("media_player.salotto", "Salotto", 0.6)])


if __name__ == "__main__":
    unittest.main()
