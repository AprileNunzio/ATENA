import asyncio
import time
import unittest
from unittest import mock

from features.desktop import secretary as secretary_mod
from features.desktop.desk import Desk
from features.desktop.news import News
from features.desktop import briefing
from features.desktop.secretary import PREFIX, SLOTS, Secretary, pick
from state import store

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Prima notizia</title></item><item><title>  Seconda   notizia </title></item>
<item><title>Prima notizia</title></item></channel></rss>"""


def _cards():
    return [("systems", ("brief", {"title": "Stato dei sistemi", "lines": ["ok"]}, 35)),
            ("resources", ("system_health", {"items": []}, 45))]


class NewsTest(unittest.TestCase):
    def test_parses_unique_titles(self):
        self.assertEqual([n["title"] for n in News.parse(RSS)], ["Prima notizia", "Seconda notizia"])

    def test_rejects_entities(self):
        with self.assertRaises(ValueError):
            News.parse(b'<!DOCTYPE x [<!ENTITY a "b">]><rss/>')

    def test_feed_outside_allowlist_falls_back(self):
        with mock.patch("features.desktop.news.env_get", return_value="https://evil.example/rss"):
            self.assertTrue(News.feed().startswith("https://www.ansa.it/"))


class SecretaryTest(unittest.TestCase):
    def setUp(self):
        self.desk = Desk()
        self.desk.scan()
        self.sec = Secretary()
        self.sec.owner_slug, self.sec.owner_at = "nunzio", time.time()
        self.saved = store.presence
        self.cards = mock.patch.object(Secretary, "cards", mock.AsyncMock(side_effect=lambda: _cards()))
        self.cards.start()
        self.env = mock.patch.object(secretary_mod, "env_get", return_value="1")
        self.env.start()

    def tearDown(self):
        self.cards.stop()
        self.env.stop()
        store.presence = self.saved

    def _see(self, near: bool | None):
        people = [] if near is None else [{"slug": "nunzio", "name": "Nunzio", "known": True, "near": near}]
        store.presence = {"status": "ok", "people": people}

    def _shown(self):
        return sorted(k for k in self.desk.instances if k.startswith(PREFIX))

    def test_opens_when_owner_comes_close(self):
        self._see(False)
        asyncio.run(self.sec.step(self.desk))
        self.assertEqual(self._shown(), [])
        self._see(True)
        asyncio.run(self.sec.step(self.desk))
        self.assertEqual(self._shown(), [PREFIX + "resources", PREFIX + "systems"])

    def test_request_clears_and_idle_reopens(self):
        self._see(True)
        asyncio.run(self.sec.step(self.desk))
        self.desk.request_started()
        asyncio.run(self.sec.step(self.desk))
        self.assertEqual(self._shown(), [])
        self._see(False)
        self.desk.went_idle()
        asyncio.run(self.sec.step(self.desk))
        self.assertEqual(len(self._shown()), 2)

    def test_closes_after_owner_leaves(self):
        self._see(True)
        asyncio.run(self.sec.step(self.desk))
        self._see(None)
        self.sec.last_seen = time.time() - 60
        asyncio.run(self.sec.step(self.desk))
        self.assertEqual(self._shown(), [])

    def test_strangers_do_not_open_it(self):
        store.presence = {"status": "ok", "people": [{"slug": "", "name": "", "known": False, "near": True}]}
        asyncio.run(self.sec.step(self.desk))
        self.assertEqual(self._shown(), [])


class VarietyTest(unittest.TestCase):
    def test_rotation_covers_every_card_and_keeps_urgent_ones(self):
        cards = [(f"c{i}", ("brief", {}, 30)) for i in range(8)] + [("alarm", ("brief", {}, 88))]
        shown_at, seen = {}, set()
        for turn in range(4):
            chosen = pick(cards, shown_at)
            self.assertIn("alarm", chosen)
            self.assertLessEqual(len(chosen), SLOTS)
            seen.update(chosen)
            shown_at.update({n: float(turn + 1) for n in chosen})
        self.assertEqual(seen, {n for n, _ in cards})

    def test_many_urgent_cards_still_leave_room_for_variety(self):
        cards = [(f"u{i}", ("brief", {}, 90)) for i in range(5)] + [("news", ("brief", {}, 30)), ("sun", ("sun_cycle", {}, 20))]
        self.assertEqual(len(pick(cards, {})), 7)

    def test_news_pages_change(self):
        items = [{"title": f"t{i}", "text": "", "image": "", "at": "", "link": ""} for i in range(7)]
        first, second = briefing.headlines(items, 0), briefing.headlines(items, 1)
        self.assertNotEqual(first[1]["lines"], second[1]["lines"])
        self.assertEqual(briefing.headlines(items, 3)[1]["lines"], first[1]["lines"])


if __name__ == "__main__":
    unittest.main()
