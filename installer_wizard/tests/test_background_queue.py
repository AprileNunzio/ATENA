import asyncio
import time
import unittest

from fastapi.testclient import TestClient

import atena_supervisor
import background
from background import BackgroundQueue
from state import store
from steps import STEP_BY_ID, STEPS

HEADERS = {"X-Atena-Request": "1"}


def fresh_queue() -> BackgroundQueue:
    q = BackgroundQueue()
    q.paused, q.order, q.last_activity = False, [], 0.0
    for s in STEPS:
        if s.background:
            store.steps.pop(s.id, None)
    return q


class QueueTest(unittest.TestCase):
    def test_large_and_optional_parts_wait_for_the_background(self):
        heavy = {s.id for s in STEPS if s.background}
        self.assertTrue({"brain", "voice", "ear", "vision", "music", "office"} <= heavy)
        self.assertFalse({"preflight", "system", "docker", "ollama", "models", "core", "services"} & heavy)
        self.assertGreater(STEP_BY_ID["brain"].size_gb, STEP_BY_ID["models"].size_gb)

    def test_order_follows_priority_and_admin_choice(self):
        q = fresh_queue()
        order = [s.id for s in q.steps()]
        self.assertLess(order.index("voice"), order.index("ear"))
        self.assertLess(order.index("ear"), order.index("brain"))
        self.assertTrue(q.prioritize("office"))
        self.assertEqual(q.steps()[0].id, "office")
        self.assertFalse(q.prioritize("core"))
        self.assertFalse(q.prioritize("missing"))

    def test_run_installs_everything_and_reports_progress(self):
        q = fresh_queue()
        background.RETRY_SECONDS = 0
        asyncio.run(asyncio.wait_for(q.run(asyncio.Lock()), timeout=120))
        snap = q.snapshot()
        self.assertTrue(snap["finished"])
        self.assertEqual(snap["done"], snap["total"])
        self.assertEqual(snap["progress"], 100.0)
        self.assertTrue(all(i["status"] == "done" for i in snap["items"]))

    def test_conversation_and_pause_hold_the_queue(self):
        q = fresh_queue()
        q.note_activity()
        self.assertTrue(q.in_conversation())
        q.last_activity = time.time() - background.CONVERSATION_QUIET_S - 1
        self.assertFalse(q.in_conversation())
        q.pause()

        async def gated() -> bool:
            try:
                await asyncio.wait_for(q._gate(), timeout=0.3)
                return True
            except asyncio.TimeoutError:
                return False
        self.assertFalse(asyncio.run(gated()))
        q.resume()
        self.assertTrue(asyncio.run(gated()))

    def test_missing_disk_space_skips_the_part(self):
        q = fresh_queue()
        q.free_gb = lambda: 1.0
        real_demo, background.DEMO = background.DEMO, False
        try:
            self.assertFalse(q._disk_ok(STEP_BY_ID["brain"]))
        finally:
            background.DEMO = real_demo
        self.assertEqual(q.snapshot()["items"][[i["id"] for i in q.snapshot()["items"]].index("brain")]["status"],
                         "waiting_disk")


class QueueApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public = TestClient(atena_supervisor.public)
        cls.admin = TestClient(atena_supervisor.admin)
        r = cls.admin.post("/api/auth/login", json={"username": "admin", "password": "atena"}, headers=HEADERS)
        assert r.status_code == 200, r.text

    def test_state_is_public_but_controls_need_admin(self):
        self.assertIn("background", self.public.get("/api/state").json())
        self.assertEqual(self.public.post("/api/background/pause", headers=HEADERS).status_code, 404)
        anon = TestClient(atena_supervisor.admin)
        self.assertEqual(anon.post("/api/background/pause", headers=HEADERS).status_code, 401)
        self.assertEqual(self.admin.post("/api/background/pause").status_code, 403)
        self.assertTrue(self.admin.post("/api/background/pause", headers=HEADERS).json()["paused"])
        self.assertFalse(self.admin.post("/api/background/resume", headers=HEADERS).json()["paused"])
        r = self.admin.post("/api/background/prioritize?step=vision", headers=HEADERS)
        self.assertEqual(r.json()["items"][0]["id"], "vision")
        self.assertEqual(self.admin.post("/api/background/prioritize?step=core", headers=HEADERS).status_code, 404)
        self.assertEqual(self.admin.post("/api/background/explode", headers=HEADERS).status_code, 404)


if __name__ == "__main__":
    unittest.main()
