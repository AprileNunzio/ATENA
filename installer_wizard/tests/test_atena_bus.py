import asyncio
import unittest

from atena_bus import BusError, AtenaBus, matches, valid_pattern


class TopicTest(unittest.TestCase):
    def test_wildcards(self):
        self.assertTrue(matches("nvr.event.*", "nvr.event.garden"))
        self.assertFalse(matches("nvr.event.*", "nvr.event.garden.extra"))
        self.assertTrue(matches("nvr.>", "nvr.event.garden.extra"))
        self.assertFalse(matches("nvr.>", "nvr"))
        self.assertTrue(matches(">", "a.b"))
        self.assertTrue(matches("a.b", "a.b"))
        self.assertFalse(matches("a.b", "a.c"))

    def test_pattern_validation(self):
        for good in ("nvr.>", "a.*.c", ">", "system.module.nvr"):
            self.assertTrue(valid_pattern(good), good)
        for bad in ("", "nvr.>.x", "NVR", "a..b", "a.b c", "../etc"):
            self.assertFalse(valid_pattern(bad), bad)


class BusTest(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.bus = AtenaBus(clock=lambda: self.now[0])

    def test_envelope_and_delivery(self):
        got = []
        self.bus.subscribe("nvr.event.*", got.append)
        env = self.bus.publish("nvr.event.garden", {"label": "person"}, origin="nvr")
        self.bus.publish("printers.status", {"x": 1})
        self.assertEqual([e.id for e in got], [env.id])
        self.assertEqual((env.topic, env.origin, env.schema, env.ts), ("nvr.event.garden", "nvr", "1.0", 100.0))

    def test_invalid_input_is_rejected(self):
        for topic in ("Bad", "a..b", "x" * 50):
            with self.assertRaises(BusError):
                self.bus.publish(topic, {})
        with self.assertRaises(BusError):
            self.bus.publish("a.b", {"blob": "x" * 70000})
        with self.assertRaises(BusError):
            self.bus.subscribe("bad pattern", print)

    def test_retained_values_replay_to_late_subscribers_and_can_be_cleared(self):
        self.bus.publish("nvr.status", {"ok": True}, retain=True)
        got = []
        self.bus.subscribe("nvr.>", got.append, replay=True)
        self.assertEqual(got[0].payload, {"ok": True})
        self.bus.publish("nvr.status", {}, retain=True)
        self.assertEqual(self.bus.retained("nvr.>"), [])

    def test_a_failing_subscriber_does_not_break_others(self):
        got = []
        self.bus.subscribe("a.b", lambda e: 1 / 0)
        self.bus.subscribe("a.b", got.append)
        self.bus.publish("a.b", {})
        self.assertEqual(len(got), 1)
        self.assertEqual(self.bus.stats()["failures"], 1)

    def test_cancelled_subscription_stops_receiving(self):
        got = []
        sub = self.bus.subscribe("a.b", got.append)
        sub.cancel()
        self.bus.publish("a.b", {})
        self.assertEqual(got, [])

    def test_discovery_announce_heartbeat_and_loss(self):
        seen = []
        self.bus.subscribe("system.discovery.*", lambda e: seen.append((e.topic, e.payload["module"])))
        self.bus.announce("nvr", ["nvr.search"], ttl=30)
        self.bus.announce("nvr", ["nvr.search"], ttl=30)
        self.assertEqual([m["module"] for m in self.bus.modules("nvr.search")], ["nvr"])
        self.now[0] += 31
        self.assertEqual(self.bus.expire(), ["nvr"])
        self.assertEqual(seen, [("system.discovery.announce", "nvr"), ("system.discovery.heartbeat", "nvr"),
                                ("system.discovery.lost", "nvr")])
        self.assertEqual(self.bus.modules(), [])
        self.assertEqual(self.bus.retained("system.module.>"), [])


class AsyncSubscriberTest(unittest.IsolatedAsyncioTestCase):
    async def test_coroutine_subscribers_run_on_the_loop(self):
        bus, got = AtenaBus(), []

        async def handler(env):
            got.append(env.topic)
        bus.subscribe("a.>", handler)
        bus.publish("a.b", {})
        await asyncio.sleep(0)
        self.assertEqual(got, ["a.b"])


if __name__ == "__main__":
    unittest.main()
