import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from access import require_admin
from features.firewall import api as firewall_api
from features.firewall import applier as applier_module
from features.firewall import events
from features.firewall import model
from features.firewall import store as store_module
from features.firewall.store import store

ALERT = {"type": "alert", "kind": "brute_force", "severity": "critical", "src": "198.51.100.7", "dst": "192.168.1.10",
         "count": 20, "detail": "20 tentativi di accesso sulla porta 22"}


class FirewallBase(unittest.TestCase):

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for target, name, value in ((store_module, "FIREWALL_DIR", root), (store_module, "CONFIG_FILE", root / "config.json"),
                                    (applier_module, "FIREWALL_DIR", root), (applier_module, "SCRIPT_FILE", root / "g.nft")):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        store.restore({})
        store.history.clear()
        self.applied: list[str] = []

        async def fake_apply(reason, confirm_seconds=0):
            self.applied.append(reason)
            return {"ok": True, "error": ""}

        patcher = mock.patch.object(applier_module.applier, "apply", side_effect=fake_apply)
        patcher.start()
        self.addCleanup(patcher.stop)
        protected = mock.patch.object(events, "protected", return_value={"192.168.1.10", "192.168.1.1"})
        protected.start()
        self.addCleanup(protected.stop)


class StoreTests(FirewallBase):

    def test_state_survives_a_restart_and_rolls_back(self):
        store.checkpoint("prima")
        store.rules["r1"] = model.rule({"id": "a1", "action": "drop", "sources": ["1.2.3.4"]})
        store.save()
        store.restore({})
        store.load()
        self.assertEqual([r.sources[0].value for r in store.rules.values()], ["1.2.3.4"])
        self.assertEqual(store.rollback()["reason"], "prima")
        self.assertEqual(store.rules, {})

    def test_corrupted_configuration_keeps_monitoring(self):
        store_module.CONFIG_FILE.write_text("{rotto", encoding="utf-8")
        store.load()
        self.assertEqual(store.policy.mode, "monitor")

    def test_trusted_networks_cover_their_addresses(self):
        store.policy = model.policy({"trusted": ["192.168.1.0/24", "aa:bb:cc:dd:ee:ff"]})
        self.assertTrue(store.trusted(model.address("192.168.1.77")))
        self.assertTrue(store.trusted(model.address("AA:BB:CC:DD:EE:FF")))
        self.assertFalse(store.trusted(model.address("10.0.0.1")))


class AutoBlockTests(FirewallBase):

    def handle(self, event):
        asyncio.run(events.monitor.handle(json.dumps(event)))

    def test_critical_attack_from_internet_is_blocked_temporarily(self):
        store.policy = model.policy({"mode": "protect", "auto_block_minutes": 30})
        self.handle(ALERT)
        block = store.blocks.get("198.51.100.7")
        self.assertIsNotNone(block)
        self.assertGreater(block.expires, 0)
        self.assertEqual(len(self.applied), 1)

    def test_monitor_mode_and_low_severity_only_record(self):
        self.handle(ALERT)
        store.policy = model.policy({"mode": "protect"})
        self.handle({**ALERT, "severity": "medium", "src": "203.0.113.5"})
        self.assertEqual(store.blocks, {})
        self.assertEqual(events.monitor.alerts[-1]["src"], "203.0.113.5")

    def test_never_blocks_itself_the_gateway_or_trusted_hosts(self):
        store.policy = model.policy({"mode": "lockdown", "trusted": ["192.168.1.50"]})
        for src in ("192.168.1.10", "192.168.1.1", "192.168.1.50"):
            self.handle({**ALERT, "src": src})
        self.assertEqual(store.blocks, {})

    def test_alerts_from_the_server_itself_are_discarded(self):
        store.policy = model.policy({"mode": "protect"})
        before = len(events.monitor.alerts)
        for src in ("127.0.0.1", "::1", "192.168.1.10"):
            self.handle({**ALERT, "kind": "port_scan", "src": src})
        self.assertEqual(len(events.monitor.alerts), before)
        self.assertEqual(store.blocks, {})
        self.handle({**ALERT, "kind": "arp_spoof", "src": "192.168.1.10"})
        self.assertEqual(len(events.monitor.alerts), before + 1)

    def test_malformed_events_are_ignored(self):
        before = len(events.monitor.alerts)
        for line in ("non json", "[]", json.dumps({"type": "alert", "kind": "rm -rf", "severity": "critical"})):
            asyncio.run(events.monitor.handle(line))
        self.assertEqual(len(events.monitor.alerts), before)

    def test_summaries_are_kept(self):
        self.handle({"type": "summary", "packets": 10, "bytes": 1000, "flows": 2, "top_talkers": []})
        self.assertEqual(events.monitor.summary["packets"], 10)


class ApiTests(FirewallBase):

    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(firewall_api.admin_routes)
        app.dependency_overrides[require_admin] = lambda: "nunzio"
        self.client = TestClient(app)

    def test_expert_can_allow_only_selected_devices(self):
        self.assertEqual(self.client.put("/api/firewall/sets/ufficio", json={"entries": ["192.168.10.0/24", "aa:bb:cc:dd:ee:ff"]}).status_code, 200)
        r = self.client.post("/api/firewall/rules", json={"action": "accept", "protocol": "tcp", "ports": ["8123"], "sources": ["@ufficio"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.put("/api/firewall/policy", json={"mode": "lockdown"}).json()["policy"]["mode"], "lockdown")
        script = self.client.get("/api/firewall/preview").json()["script"]
        self.assertIn("policy drop;", script)
        self.assertIn("ip saddr @ufficio_4 meta l4proto tcp tcp dport { 8123 } counter accept", script)

    def test_invalid_changes_are_rejected_and_nothing_changes(self):
        before = store.snapshot()
        self.assertEqual(self.client.post("/api/firewall/rules", json={"action": "drop", "sources": ["1.2.3.4; flush ruleset"]}).status_code, 400)
        self.assertEqual(self.client.delete("/api/firewall/rules/nessuna").status_code, 400)
        self.assertEqual(store.snapshot(), before)

    def test_groups_in_use_cannot_be_deleted(self):
        self.client.put("/api/firewall/sets/casa", json={"entries": ["10.0.0.0/8"]})
        self.client.post("/api/firewall/rules", json={"action": "drop", "sources": ["@casa"]})
        self.assertEqual(self.client.delete("/api/firewall/sets/casa").status_code, 400)

    def test_blocks_and_rollback(self):
        self.client.post("/api/firewall/blocks", json={"address": "203.0.113.9", "minutes": 10})
        self.assertIn("203.0.113.9", [b["address"] for b in self.client.get("/api/firewall").json()["blocks"]])
        self.assertEqual(self.client.post("/api/firewall/rollback").json()["blocks"], [])

    def test_rejected_by_nftables_restores_the_previous_state(self):
        async def refuse(reason, confirm_seconds=0):
            if reason.startswith("nuova regola"):
                raise applier_module.FirewallError("syntax error")
            return {"ok": True}

        with mock.patch.object(applier_module.applier, "apply", side_effect=refuse):
            r = self.client.post("/api/firewall/rules", json={"action": "drop", "sources": ["1.2.3.4"]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(store.rules, {})


class ApplierTests(unittest.TestCase):

    def test_unconfirmed_changes_are_reverted(self):
        applier = applier_module.Applier()
        reverted = []

        async def scenario():
            with mock.patch.object(store_module.store, "rollback", return_value={"reason": "prova"}), \
                    mock.patch.object(applier, "apply", side_effect=lambda reason, *_: reverted.append(reason)):
                applier._arm(0)
                task = asyncio.get_running_loop().create_task(applier._revert_after(0))
                await task

        asyncio.run(scenario())
        self.assertEqual(reverted, ["ripristino automatico"])

    def test_confirmation_cancels_the_revert(self):
        applier = applier_module.Applier()

        async def scenario():
            applier._arm(60)
            self.assertGreater(applier.deadline, 0)
            self.assertTrue(applier.confirm())
            self.assertEqual(applier.deadline, 0.0)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
