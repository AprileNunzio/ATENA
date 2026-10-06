import asyncio
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

import loops
from features.automations.schema import validate
from features.scheduler import cronexpr, misfire
from features.scheduler.clock import TriggerClock
from features.scheduler.marks import Marks


def at(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


class CronTest(unittest.TestCase):
    def nxt(self, expr, after):
        return cronexpr.next_after(cronexpr.parse(expr), at(after)).strftime("%Y-%m-%d %H:%M")

    def test_basic_steps_ranges_and_lists(self):
        self.assertEqual(self.nxt("*/15 * * * *", "2026-10-04 10:07"), "2026-10-04 10:15")
        self.assertEqual(self.nxt("0 8-18/5 * * *", "2026-10-04 08:00"), "2026-10-04 13:00")
        self.assertEqual(self.nxt("5,35 9 * * *", "2026-10-04 09:10"), "2026-10-04 09:35")
        self.assertEqual(self.nxt("30 6 * * *", "2026-10-04 06:30"), "2026-10-05 06:30")

    def test_weekday_names_and_sunday_as_seven(self):
        self.assertEqual(self.nxt("0 9 * * mon-fri", "2026-10-03 12:00"), "2026-10-05 09:00")
        self.assertEqual(self.nxt("0 9 * * 7", "2026-10-04 12:00"), "2026-10-11 09:00")
        self.assertEqual(self.nxt("0 9 * * 0", "2026-10-04 08:00"), "2026-10-04 09:00")

    def test_day_of_month_or_weekday_when_both_restricted(self):
        self.assertEqual(self.nxt("0 0 13 * fri", "2026-10-01 00:00"), "2026-10-02 00:00")
        self.assertEqual(self.nxt("0 0 13 * fri", "2026-10-03 00:00"), "2026-10-09 00:00")

    def test_month_names_and_month_end(self):
        self.assertEqual(self.nxt("0 0 1 jan *", "2026-10-04 00:00"), "2027-01-01 00:00")
        self.assertEqual(self.nxt("0 0 31 * *", "2026-11-01 00:00"), "2026-12-31 00:00")
        self.assertEqual(self.nxt("0 0 29 2 *", "2026-03-01 00:00"), "2028-02-29 00:00")

    def test_aliases(self):
        self.assertEqual(self.nxt("@hourly", "2026-10-04 10:07"), "2026-10-04 11:00")
        self.assertEqual(self.nxt("@daily", "2026-10-04 10:07"), "2026-10-05 00:00")
        self.assertEqual(self.nxt("@weekly", "2026-10-04 10:07"), "2026-10-11 00:00")

    def test_invalid_expressions_explain_the_problem(self):
        for bad in ("", "* * * *", "61 * * * *", "* 24 * * *", "*/0 * * * *", "5-1 * * * *", "a * * * *", "* * 32 * *", ", * * * *"):
            with self.assertRaises(cronexpr.CronError, msg=bad):
                cronexpr.parse(bad)
        with self.assertRaises(cronexpr.CronError):
            cronexpr.next_after(cronexpr.parse("0 0 31 2 *"), at("2026-01-01 00:00"))

    def test_fires_between_is_bounded_and_ordered(self):
        spec = cronexpr.parse("*/10 * * * *")
        fires = cronexpr.fires_between(spec, at("2026-10-04 10:00"), at("2026-10-04 11:00"))
        self.assertEqual([f.strftime("%H:%M") for f in fires], ["10:10", "10:20", "10:30", "10:40", "10:50", "11:00"])
        every = cronexpr.parse("* * * * *")
        self.assertEqual(len(cronexpr.fires_between(every, at("2026-01-01 00:00"), at("2026-12-31 00:00"), limit=50)), 50)


class MisfireTest(unittest.TestCase):
    def setUp(self):
        self.now = at("2026-10-04 12:00")
        self.fires = [at("2026-10-04 10:30"), at("2026-10-04 11:00"), at("2026-10-04 11:30")]

    def test_skip_run_once_run_all(self):
        self.assertEqual(misfire.plan(self.fires, "skip", 7200, self.now, 3), [])
        self.assertEqual(misfire.plan(self.fires, "run_once", 7200, self.now, 3), [self.fires[-1]])
        self.assertEqual(misfire.plan(self.fires, "run_all", 7200, self.now, 2), self.fires[-2:])

    def test_grace_window_excludes_old_misses_and_zero_disables(self):
        self.assertEqual(misfire.plan(self.fires, "run_all", 3700, self.now, 9), self.fires[1:])
        self.assertEqual(misfire.plan(self.fires, "run_all", 0, self.now, 9), [])

    def test_interval_verdicts(self):
        self.assertEqual(misfire.interval_overdue(1000, 600, 1500, "run_once", 3600), "wait")
        self.assertEqual(misfire.interval_overdue(1000, 600, 1650, "run_once", 3600), "run")
        self.assertEqual(misfire.interval_overdue(1000, 600, 3000, "run_once", 3600), "run")
        self.assertEqual(misfire.interval_overdue(1000, 600, 3000, "skip", 3600), "reset")
        self.assertEqual(misfire.interval_overdue(1000, 600, 99999, "run_once", 3600), "reset")

    def test_policy_parsing(self):
        self.assertEqual(misfire.policy_of("RUN_ALL", "skip"), "run_all")
        self.assertEqual(misfire.policy_of("boh", "run_once"), "run_once")


class ClockTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.file = self.dir / "scheduler.json"
        self.env = {}
        self.started = []

    def clock(self):
        return TriggerClock(Marks(self.file), lambda a, t: self.started.append((a["id"], t["label"])), lambda k, d="": self.env.get(k, d))

    @staticmethod
    def auto(trigger, aid="a1"):
        return {"id": aid, "name": aid, "enabled": True, "triggers": [{"id": "t1", **trigger}]}

    def test_time_trigger_fires_once_per_minute(self):
        clock = self.clock()
        autos = [self.auto({"type": "time", "at": "7:30", "days": [6]})]
        clock.tick(autos, at("2026-10-04 07:29"))
        clock.tick(autos, at("2026-10-04 07:30"))
        clock.tick(autos, at("2026-10-04 07:30"))
        clock.tick(autos, at("2026-10-05 07:30"))
        self.assertEqual(len(self.started), 1)

    def test_cron_trigger_fires_on_match(self):
        clock = self.clock()
        autos = [self.auto({"type": "cron", "expr": "*/15 * * * *"})]
        for minute in ("10:00", "10:07", "10:15", "10:30"):
            clock.tick(autos, at(f"2026-10-04 {minute}"))
        self.assertEqual(len(self.started), 3)

    def test_invalid_cron_never_fires_and_does_not_crash(self):
        clock = self.clock()
        clock.tick([self.auto({"type": "cron", "expr": "nonsense"})], at("2026-10-04 10:00"))
        self.assertEqual(self.started, [])

    def test_missed_run_is_recovered_once_after_restart(self):
        autos = [self.auto({"type": "cron", "expr": "0 * * * *"})]
        first = self.clock()
        first.marks.set("a1:t1", at("2026-10-04 09:00").timestamp(), now_flush=True)
        second = self.clock()
        second.tick(autos, at("2026-10-04 11:20"))
        self.assertEqual(len(self.started), 1)
        self.assertIn("recupero", self.started[0][1])

    def test_skip_policy_and_grace_prevent_recovery(self):
        autos = [self.auto({"type": "cron", "expr": "0 * * * *"})]
        base = self.clock()
        base.marks.set("a1:t1", at("2026-10-04 09:00").timestamp(), now_flush=True)
        self.env["ATENA_SCHED_MISFIRE"] = "skip"
        self.clock().tick(autos, at("2026-10-04 11:20"))
        self.assertEqual(self.started, [])
        self.env.update(ATENA_SCHED_MISFIRE="run_once", ATENA_SCHED_GRACE_MIN="10")
        self.clock().tick(autos, at("2026-10-04 11:20"))
        self.assertEqual(self.started, [])

    def test_trigger_level_override_beats_global_policy(self):
        autos = [self.auto({"type": "cron", "expr": "0 * * * *", "misfire": "skip"})]
        base = self.clock()
        base.marks.set("a1:t1", at("2026-10-04 09:00").timestamp(), now_flush=True)
        self.clock().tick(autos, at("2026-10-04 11:20"))
        self.assertEqual(self.started, [])

    def test_persistence_can_be_switched_off(self):
        self.env["ATENA_SCHED_PERSIST"] = "0"
        clock = self.clock()
        clock.tick([self.auto({"type": "cron", "expr": "0 * * * *"})], at("2026-10-04 10:00"))
        self.assertFalse(self.file.exists())

    def test_interval_survives_restart_without_resetting(self):
        autos = [self.auto({"type": "interval", "minutes": 10})]
        first = self.clock()
        first.marks.set("a1:t1", time.time() - 700, now_flush=True)
        second = self.clock()
        second.tick(autos)
        self.assertEqual(len(self.started), 1)

    def test_interval_far_overdue_with_skip_resets_silently(self):
        autos = [self.auto({"type": "interval", "minutes": 10})]
        self.env["ATENA_SCHED_MISFIRE"] = "skip"
        first = self.clock()
        first.marks.set("a1:t1", time.time() - 7200, now_flush=True)
        self.clock().tick(autos)
        self.assertEqual(self.started, [])

    def test_disabled_automation_is_ignored_and_upcoming_is_sorted(self):
        clock = self.clock()
        off = {**self.auto({"type": "cron", "expr": "* * * * *"}, "off"), "enabled": False}
        clock.tick([off], at("2026-10-04 10:00"))
        self.assertEqual(self.started, [])
        autos = [self.auto({"type": "cron", "expr": "0 23 * * *"}, "late"), self.auto({"type": "cron", "expr": "30 10 * * *"}, "soon")]
        rows = clock.upcoming(autos, at("2026-10-04 10:00"))
        self.assertEqual([r["id"] for r in rows], ["soon", "late"])

    def test_corrupt_state_file_is_ignored(self):
        self.file.write_text("{non json", encoding="utf-8")
        self.assertEqual(Marks(self.file).data, {})


class SchemaTest(unittest.TestCase):
    def base(self, trigger):
        return {"name": "x", "triggers": [trigger], "actions": [{"type": "speak", "text": "ciao"}]}

    def test_cron_trigger_is_validated(self):
        _, errors = validate(self.base({"type": "cron", "expr": "*/5 * * * *"}))
        self.assertEqual([e for e in errors if "cron" in e.lower()], [])
        _, errors = validate(self.base({"type": "cron", "expr": "99 * * * *"}))
        self.assertTrue(any("cron" in e.lower() for e in errors))


class LoopsTest(unittest.TestCase):
    def setUp(self):
        self.old = (loops.BACKOFF_MIN, loops.CHECK_EVERY, loops.stale_factor, loops.backoff_max)
        loops.BACKOFF_MIN, loops.CHECK_EVERY = 0.01, 0.02
        loops.stale_factor = lambda: 2.0
        loops.backoff_max = lambda: 0.05

    def tearDown(self):
        loops.BACKOFF_MIN, loops.CHECK_EVERY, loops.stale_factor, loops.backoff_max = self.old

    @staticmethod
    def drive(sup, seconds):
        async def go():
            task = asyncio.create_task(sup.run())
            await asyncio.sleep(seconds)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        asyncio.run(go())

    def test_crashing_loop_is_restarted_with_backoff(self):
        sup, runs = loops.Supervisor(), []

        async def crash():
            runs.append(1)
            raise RuntimeError("guasto")
        sup.add("crash", crash)
        self.drive(sup, 0.4)
        self.assertGreaterEqual(len(runs), 3)
        view = sup.snapshot()[0]
        self.assertIn("guasto", view["last_error"])
        self.assertGreaterEqual(view["restarts"], 3)

    def test_loop_that_finishes_normally_is_not_restarted(self):
        sup, runs = loops.Supervisor(), []

        async def once():
            runs.append(1)
        sup.add("once", once)
        self.drive(sup, 0.2)
        self.assertEqual(len(runs), 1)
        self.assertEqual(sup.snapshot()[0]["state"], "concluso")

    def test_stalled_loop_is_cancelled_and_restarted(self):
        sup, runs = loops.Supervisor(), []

        async def stuck():
            runs.append(1)
            await asyncio.sleep(60)
        sup.add("stuck", stuck, period=0.02)
        self.drive(sup, 0.5)
        self.assertGreaterEqual(len(runs), 2)
        self.assertGreaterEqual(sup.snapshot()[0]["stalls"], 1)

    def test_healthy_loop_with_heartbeat_is_left_alone(self):
        sup, runs = loops.Supervisor(), []

        async def healthy():
            runs.append(1)
            while True:
                sup.beat("ok")
                await asyncio.sleep(0.01)
        sup.add("ok", healthy, period=0.02)
        self.drive(sup, 0.3)
        self.assertEqual(len(runs), 1)
        self.assertEqual(sup.totals()["stalls"], 0)

    def test_one_failing_loop_does_not_stop_the_others(self):
        sup, good = loops.Supervisor(), []

        async def bad():
            raise ValueError("x")

        async def fine():
            while True:
                good.append(1)
                await asyncio.sleep(0.01)
        sup.add("bad", bad)
        sup.add("fine", fine)
        self.drive(sup, 0.2)
        self.assertGreater(len(good), 5)


if __name__ == "__main__":
    unittest.main()
