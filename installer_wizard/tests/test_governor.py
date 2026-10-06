import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from features.governor import conf, devices, pressure, profile
from features.governor.ledger import Ledger
from features.governor.service import Governor


class PressureTest(unittest.TestCase):
    def test_score_takes_the_worst_resource(self):
        self.assertEqual(pressure.score(10, 40, 0, 0.1), 10.0)
        self.assertEqual(pressure.score(10, 95, 0, 0.1), 90.0)
        self.assertEqual(pressure.score(10, 40, 100, 0.0), 100.0)
        self.assertEqual(pressure.score(500, 500, 500, 50), 100.0)

    def test_hysteresis_avoids_flapping(self):
        p = pressure.Pressure(alpha=1.0)
        states = []
        for raw in (50, 80, 70, 60, 56, 54, 70, 90):
            p.update(raw, 75, 55, time.time())
            states.append(p.high)
        self.assertEqual(states, [False, True, True, True, True, False, False, True])

    def test_smoothing_ignores_a_single_spike(self):
        p = pressure.Pressure(alpha=0.4)
        for _ in range(5):
            p.update(20, 75, 55, 0)
        p.update(100, 75, 55, 0)
        self.assertFalse(p.high)


class ProfileTest(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(profile.classify(2, 8, True), "low")
        self.assertEqual(profile.classify(8, 2, True), "low")
        self.assertEqual(profile.classify(4, 16, False), "low")
        self.assertEqual(profile.classify(8, 16, False), "mid")
        self.assertEqual(profile.classify(12, 32, True), "high")
        self.assertEqual(profile.classify(4, 8, True), "mid")

    def test_every_class_defines_every_job_kind(self):
        for cls in profile.CLASSES:
            self.assertEqual(set(profile.SLOTS[cls]), set(profile.JOB_KINDS))
            self.assertIn(cls, profile.WIDGETS)


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(Path(tempfile.mkdtemp()) / "g.db")

    def test_records_accumulate_and_rank_by_cost(self):
        for _ in range(3):
            self.ledger.record("a", "job", 5, 10, 100)
        self.ledger.record("b", "job", 1, 500, 10)
        top = self.ledger.top(5)
        self.assertEqual([r["component"] for r in top], ["b", "a"])
        a = next(r for r in top if r["component"] == "a")
        self.assertEqual((a["calls"], a["avg_wall_ms"], a["avg_size"]), (3, 10.0, 100.0))

    def test_estimate_scales_with_content_size(self):
        self.ledger.record("doc", "job", 40, 100, 10)
        self.ledger.record("doc", "job", 60, 300, 30)
        base = self.ledger.estimate("doc")
        self.assertEqual(base["samples"], 2)
        big = self.ledger.estimate("doc", size=40)
        self.assertAlmostEqual(big["avg_wall_ms"], 200.0 * 2, places=1)
        self.assertIsNone(self.ledger.estimate("sconosciuto"))

    def test_samples_history_clear_and_prune(self):
        self.ledger.sample(10, 50, 0, 0.5, 20, None)
        self.ledger.sample(30, 60, 0, 0.7, 40, 55.0)
        history = self.ledger.history(5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["cpu"], 20.0)
        self.assertEqual(history[0]["pressure"], 40.0)
        self.ledger.record("x", "job", 1, 1)
        self.ledger.prune(-1.0)
        self.assertEqual(self.ledger.top(5), [])
        self.ledger.record("y", "job", 1, 1)
        self.ledger.clear()
        self.assertEqual(self.ledger.top(5), [])


class DevicesTest(unittest.TestCase):
    def report(self, **kw):
        base = {"device": "abcdef12", "fps": 30, "p95": 20, "widgets": [], "visible": True}
        return devices.clean_report({**base, **kw})

    def test_clean_report_rejects_and_clamps(self):
        self.assertIsNone(devices.clean_report({"device": "x"}))
        self.assertIsNone(devices.clean_report("no"))
        r = self.report(fps=9999, p95=-5, widgets=[{"id": "meteo", "ms": 1e9, "nodes": 5}, {"id": "../x", "ms": 1}, "no"])
        self.assertEqual((r["fps"], r["p95"]), (240, 0))
        self.assertEqual([w["id"] for w in r["widgets"]], ["meteo"])
        self.assertEqual(r["widgets"][0]["ms"], 60000)

    def test_verdicts(self):
        self.assertEqual(devices.verdict(self.report(fps=0)), "idle")
        self.assertEqual(devices.verdict(self.report(visible=False)), "idle")
        self.assertEqual(devices.verdict(self.report(fps=5, p95=200)), "bad")
        self.assertEqual(devices.verdict(self.report(fps=20, p95=50)), "slow")
        self.assertEqual(devices.verdict(self.report(fps=30, p95=20)), "good")
        self.assertEqual(devices.verdict(self.report(fps=20, p95=35)), "ok")

    def test_tier_worsens_after_repeated_bad_and_recovers_slowly(self):
        self.assertEqual(devices.next_tier("full", ["bad"]), "full")
        self.assertEqual(devices.next_tier("full", ["bad", "bad"]), "reduced")
        self.assertEqual(devices.next_tier("reduced", ["slow", "bad"]), "minimal")
        self.assertEqual(devices.next_tier("minimal", ["bad", "bad"]), "minimal")
        self.assertEqual(devices.next_tier("full", ["slow", "slow", "slow"]), "reduced")
        self.assertEqual(devices.next_tier("reduced", ["good"] * 5), "reduced")
        self.assertEqual(devices.next_tier("reduced", ["good"] * 6), "full")
        self.assertEqual(devices.next_tier("full", ["good"] * 8), "full")

    def test_device_state_persists_and_respects_the_minimum_gap(self):
        path = Path(tempfile.mkdtemp()) / "d.json"
        store = devices.Devices(path)
        bad = self.report(fps=4, p95=300)
        now = 1000.0
        tier, _ = store.apply(bad, "full", now)
        self.assertEqual(tier, "full")
        tier, _ = store.apply(bad, "full", now + 1)
        self.assertEqual(len(store.data["abcdef12"]["history"]), 1)
        tier, changed = store.apply(bad, "full", now + 20)
        self.assertEqual((tier, changed), ("reduced", True))
        store.save(force=True)
        self.assertEqual(devices.Devices(path).known("abcdef12")["tier"], "reduced")
        store.forget("abcdef12")
        self.assertIsNone(store.known("abcdef12")["tier"])

    def test_corrupt_file_is_ignored(self):
        path = Path(tempfile.mkdtemp()) / "d.json"
        path.write_text("{no", encoding="utf-8")
        self.assertEqual(devices.Devices(path).data, {})


class GovernorTest(unittest.TestCase):
    def setUp(self):
        self.gov = Governor()
        self.gov.ledger = Ledger(Path(tempfile.mkdtemp()) / "g.db")
        self.gov.devices = devices.Devices(Path(tempfile.mkdtemp()) / "d.json")
        self.settings = {}
        self.patches = [
            mock.patch.object(conf, "flag", lambda k, d=True: self.settings.get(k, d)),
            mock.patch.object(conf, "number", lambda k, d, lo, hi: self.settings.get(k, d)),
            mock.patch.object(conf, "choice", lambda k, d, allowed: self.settings.get(k, d)),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def test_gate_never_delays_interactive_or_realtime(self):
        self.gov.pressure.high = True
        for kind in ("realtime", "interactive"):
            self.assertEqual(asyncio.run(self.gov.gate(kind, "x")), 0.0)

    def test_background_waits_until_pressure_drops(self):
        self.gov.pressure.high = True

        async def go():
            async def relief():
                await asyncio.sleep(0.05)
                self.gov.pressure.high = False
            with mock.patch("features.governor.service.DEFER_STEP", 0.01):
                task = asyncio.create_task(relief())
                waited = await self.gov.gate("background", "job")
                await task
            return waited
        waited = asyncio.run(go())
        self.assertGreater(waited, 0.03)
        self.assertEqual(self.gov.deferred["count"], 1)

    def test_deferral_is_bounded_by_the_maximum(self):
        self.gov.pressure.high = True
        self.settings["ATENA_GOV_DEFER_MAX_MIN"] = 0.0
        self.assertEqual(asyncio.run(self.gov.gate("background", "job")), 0.0)

    def test_disabled_governor_is_transparent(self):
        self.settings["ATENA_GOVERNOR"] = False
        self.gov.pressure.high = True
        self.assertEqual(asyncio.run(self.gov.gate("background", "job")), 0.0)
        with self.gov.measure("x"):
            pass
        self.assertEqual(self.gov.ledger.top(5), [])

    def test_slot_limits_concurrency_and_records_cost(self):
        self.settings["ATENA_GOV_CLASS"] = "low"
        peak = {"now": 0, "max": 0}

        async def work(name):
            async with self.gov.slot("background", name, size=3):
                peak["now"] += 1
                peak["max"] = max(peak["max"], peak["now"])
                await asyncio.sleep(0.02)
                peak["now"] -= 1

        async def go():
            await asyncio.gather(*(work(f"j{i}") for i in range(4)))
        asyncio.run(go())
        self.assertEqual(peak["max"], 1)
        self.assertEqual(len(self.gov.ledger.top(5)), 4)
        self.assertEqual(self.gov.active["background"], 0)

    def test_policy_follows_class_override_and_device_history(self):
        self.settings["ATENA_GOV_CLASS"] = "low"
        policy = self.gov.policy(None)
        self.assertEqual((policy["class"], policy["tier"], policy["max_active"]), ("low", "reduced", 2))
        self.settings["ATENA_GOV_CLASS"] = "high"
        self.assertEqual(self.gov.policy(None)["tier"], "full")
        self.settings["ATENA_GOV_MAX_WIDGETS"] = 3
        self.assertEqual(self.gov.policy(None)["max_active"], 3)
        self.settings["ATENA_GOV_QUALITY"] = "minimal"
        policy = self.gov.policy(None)
        self.assertEqual((policy["tier"], policy["max_ambient"]), ("minimal", 0))

    def test_report_updates_ledger_and_lowers_the_tier_for_a_slow_device(self):
        self.settings["ATENA_GOV_CLASS"] = "high"
        slow = devices.clean_report({"device": "slowpc01", "fps": 4, "p95": 300, "active": 3,
                                     "widgets": [{"id": "viewer_3d", "ms": 900, "nodes": 4000}]})
        first = self.gov.report(slow)
        self.gov.devices.data["slowpc01"]["last"] -= 100
        second = self.gov.report(slow)
        self.assertEqual(first["tier"], "full")
        self.assertEqual(second["tier"], "reduced")
        self.assertTrue(second["changed"])
        self.assertEqual(self.gov.policy("slowpc01")["tier"], "reduced")
        self.assertEqual(self.gov.policy("otherpc1")["tier"], "full")
        self.assertEqual(self.gov.ledger.top(5)[0]["component"], "widget:viewer_3d")

    def test_state_is_serialisable(self):
        import json
        json.dumps(self.gov.state())


if __name__ == "__main__":
    unittest.main()
