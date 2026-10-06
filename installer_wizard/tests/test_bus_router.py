import itertools
import os
import unittest

import bus_router
from bus_router import PyTopicRouter, py_matches, py_valid_origin, py_valid_pattern, py_valid_topic

try:
    import atena_native
except ImportError:
    atena_native = None

PATTERNS = ("a", "a.b", "a.*", "*.b", "a.>", "*.>", ">", "a.*.c", "*.*.*", "b.>", "a.b.c", "*")
TOPICS = ("a", "b", "a.b", "a.c", "b.b", "a.b.c", "a.x.c", "b.c.d", "a.b.c.d", "a.b.c.d.e.f.g.h")
BAD_TOPICS = ("", "Bad", "a..b", "a.*", "a.>", ".a", "a.", "a.b\n", "a.b.c.d.e.f.g.h.i", "è", "x" * 41)
BAD_PATTERNS = ("", "nvr.>.x", "NVR", "a..b", "a.b c", "../etc", ".>", "a.>.>", "a.**", "a.b\n", "a.b.c.d.e.f.g.h.i")


class RouterContract:
    def make(self):
        raise NotImplementedError

    def test_routes_like_linear_matching_in_subscription_order(self):
        router = self.make()
        ids = [router.subscribe(p) for p in PATTERNS]
        for topic in TOPICS:
            expected = [sid for p, sid in zip(PATTERNS, ids) if py_matches(p, topic)]
            self.assertEqual(list(router.route(topic)), expected, topic)

    def test_unsubscribe(self):
        router = self.make()
        sid = router.subscribe("a.>")
        self.assertTrue(router.unsubscribe(sid))
        self.assertFalse(router.unsubscribe(sid))
        self.assertEqual(list(router.route("a.b")), [])
        self.assertEqual(len(router), 0)

    def test_rejects_invalid_input(self):
        router = self.make()
        for pattern in BAD_PATTERNS:
            with self.assertRaises(ValueError, msg=pattern):
                router.subscribe(pattern)
        for topic in BAD_TOPICS:
            with self.assertRaises(ValueError, msg=topic):
                router.route(topic)


class PyRouterTest(RouterContract, unittest.TestCase):
    def make(self):
        return PyTopicRouter()


@unittest.skipIf(atena_native is None, "atena_native not built")
class NativeRouterTest(RouterContract, unittest.TestCase):
    def make(self):
        return atena_native.TopicRouter()

    def test_validators_agree_with_python(self):
        for pattern, topic in itertools.product(PATTERNS + BAD_PATTERNS, TOPICS + BAD_TOPICS):
            self.assertEqual(atena_native.matches(pattern, topic), py_matches(pattern, topic), (pattern, topic))
        for raw in PATTERNS + BAD_PATTERNS + TOPICS + BAD_TOPICS + ("node.kitchen-1", "o" * 65):
            self.assertEqual(atena_native.valid_topic(raw), py_valid_topic(raw), raw)
            self.assertEqual(atena_native.valid_pattern(raw), py_valid_pattern(raw), raw)
            self.assertEqual(atena_native.valid_origin(raw), py_valid_origin(raw), raw)

    def test_bus_uses_the_native_engine_unless_disabled(self):
        disabled = os.environ.get("ATENA_NATIVE", "auto").strip() == "0"
        self.assertEqual(bus_router.ENGINE, "python" if disabled else "rust")


if __name__ == "__main__":
    unittest.main()
