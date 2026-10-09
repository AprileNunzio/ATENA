import time
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from features.desktop.desk import SNOOZE, Desk
from features.desktop.news import News
from features.nodes import display_link
from features.nodes.display_link import COOKIE, DisplayLinks

RSS = b"""<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
<item><title>Titolo &amp; uno</title><description><![CDATA[<p>Testo <b>completo</b></p>]]></description>
<link>https://www.ansa.it/a</link><enclosure url="https://img.ansa.it/a.jpg" type="image/jpeg"/></item>
<item><title>Due</title><link>javascript:alert(1)</link><media:content url="http://insecure/x.jpg"/></item>
</channel></rss>"""


class SnoozeTest(unittest.TestCase):
    def setUp(self):
        self.desk = Desk()
        self.desk.scan()

    def test_closed_auto_widget_stays_closed_until_snooze_ends_or_data_changes(self):
        self.desk.show("brief", {"title": "Notizie", "lines": ["a"]}, key="briefing:news")
        self.assertTrue(self.desk.dismiss("briefing:news"))
        self.desk.show("brief", {"title": "Notizie", "lines": ["b"]}, key="briefing:news")
        self.assertNotIn("briefing:news", self.desk.instances)
        data, _ = self.desk.dismissed["briefing:news"]
        self.desk.dismissed["briefing:news"] = (data, time.time() - SNOOZE - 1)
        self.desk.show("brief", {"title": "Notizie", "lines": ["a"]}, key="briefing:news")
        self.assertNotIn("briefing:news", self.desk.instances)
        self.desk.show("brief", {"title": "Notizie", "lines": ["c"]}, key="briefing:news")
        self.assertIn("briefing:news", self.desk.instances)

    def test_urgent_and_requested_widgets_are_never_snoozed(self):
        self.desk.show("alarm", {"title": "Fumo"}, key="alarm:smoke:")
        self.desk.dismiss("alarm:smoke:")
        self.desk.show("alarm", {"title": "Fumo"}, key="alarm:smoke:")
        self.assertIn("alarm:smoke:", self.desk.instances)
        self.desk.show("weather", {}, key="w", intent=True)
        self.desk.dismiss("w")
        self.assertNotIn("w", self.desk.dismissed)
        self.assertFalse(self.desk.dismiss("missing"))


class WakeTest(unittest.TestCase):
    def test_wake_closes_only_automatic_widgets_and_pauses_the_secretary(self):
        desk = Desk()
        desk.scan()
        desk.show("brief", {"lines": ["x"]}, key="briefing:news")
        desk.show("weather", {}, key="welcome:weather", intent=True)
        desk.show("notice", {"title": "Allarme acqua"}, key="net:aa")
        desk.show("alarm", {"title": "Fumo"}, key="alarm:smoke:")
        self.assertEqual(desk.wake(), 2)
        self.assertEqual(sorted(desk.instances), ["alarm:smoke:", "net:aa"])
        self.assertTrue(desk.in_request())
        desk.went_idle()
        self.assertFalse(desk.in_request())


class NewsDetailTest(unittest.TestCase):
    def test_items_carry_safe_details(self):
        first, second = News.parse(RSS)
        self.assertEqual(first["title"], "Titolo & uno")
        self.assertEqual(first["text"], "Testo completo")
        self.assertEqual(first["image"], "https://img.ansa.it/a.jpg")
        self.assertEqual(second["link"], "")
        self.assertEqual(second["image"], "")


class DisplayLinkTest(unittest.TestCase):
    def setUp(self):
        self.links = DisplayLinks()
        self.nodes = mock.patch.object(display_link.registry, "data", {"nodes": {"pc1": {"id": "pc1", "name": "PC studio"}}})
        self.nodes.start()
        self.addCleanup(self.nodes.stop)

    def test_link_is_single_use_and_session_follows_the_node(self):
        token = self.links.issue("pc1")
        session, node = self.links.redeem(token)
        self.assertEqual(node, "pc1")
        self.assertIsNone(self.links.redeem(token))
        self.assertEqual(self.links.node_of(session), "pc1")
        display_link.registry.data["nodes"].pop("pc1")
        self.assertIsNone(self.links.node_of(session))

    def test_expired_link_is_refused(self):
        token = self.links.issue("pc1")
        with mock.patch.object(display_link.time, "time", return_value=time.time() + 120):
            self.assertIsNone(self.links.redeem(token))

    def test_open_route_sets_a_strict_cookie(self):
        app = FastAPI()
        app.include_router(display_link.public_routes)
        http = TestClient(app)
        with mock.patch.object(display_link, "links", self.links):
            token = self.links.issue("pc1")
            res = http.get(f"/screen/open?t={token}", follow_redirects=False)
            self.assertEqual(res.status_code, 303)
            self.assertEqual(res.headers["location"], "/screen?mirror=1")
            cookie = res.headers["set-cookie"].lower()
            self.assertIn(COOKIE, cookie)
            self.assertIn("httponly", cookie)
            self.assertIn("samesite=strict", cookie)
            self.assertEqual(http.get(f"/screen/open?t={token}", follow_redirects=False).status_code, 403)


if __name__ == "__main__":
    unittest.main()
