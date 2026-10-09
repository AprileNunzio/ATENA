import os
import shutil
import subprocess
import tempfile
import unittest

from features.firewall import model, nft

NOW = 1_800_000_000.0


def _compile(mode="protect", rules=(), sets=None, blocks=(), **policy):
    return nft.compile_script(model.policy({"mode": mode, **policy}), [model.rule(r) for r in rules],
                              {k: model.address_set(k, v) for k, v in (sets or {}).items()}, list(blocks), NOW)


class ModelTests(unittest.TestCase):

    def test_addresses_are_normalised(self):
        self.assertEqual(model.address("192.168.1.10/24"), model.Address("ip4", "192.168.1.0/24"))
        self.assertEqual(model.address("10.0.0.7"), model.Address("ip4", "10.0.0.7"))
        self.assertEqual(model.address("2001:DB8::1"), model.Address("ip6", "2001:db8::1"))
        self.assertEqual(model.address("AA-BB-CC-DD-EE-FF"), model.Address("mac", "aa:bb:cc:dd:ee:ff"))
        self.assertEqual(model.address("@ufficio"), model.Address("set", "ufficio"))

    def test_injection_attempts_are_rejected(self):
        for bad in ('1.2.3.4; flush ruleset', '@x"}', "eth0 accept", "${HOME}", "1.2.3.4\naccept"):
            with self.assertRaises(ValueError):
                model.address(bad)
        with self.assertRaises(ValueError):
            model.rule({"action": "drop", "interface": 'eth0" accept'})
        self.assertEqual(model.comment('ciao"; flush ruleset'), "ciao flush ruleset")

    def test_rule_consistency_is_enforced(self):
        cases = [{"action": "drop", "ports": ["22"]}, {"action": "limit", "protocol": "tcp"},
                 {"action": "drop", "destinations": ["aa:bb:cc:dd:ee:ff"]},
                 {"action": "drop", "direction": "output", "sources": ["aa:bb:cc:dd:ee:ff"]},
                 {"action": "allow"}, {"action": "drop", "protocol": "tcp", "ports": ["70000"]},
                 {"action": "limit", "protocol": "tcp", "rate": "fast"}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                model.rule(case)

    def test_rules_round_trip(self):
        r = model.rule({"action": "limit", "protocol": "tcp", "ports": "22, 8000-8100", "rate": "10/minute burst 5",
                        "sources": ["@ufficio", "1.2.3.4"], "comment": "SSH"})
        again = model.rule(r.export())
        self.assertEqual((again.ports, again.rate, again.sources), (["22", "8000-8100"], "10/minute burst 5 packets", r.sources))

    def test_policy_merges_and_validates(self):
        p = model.policy({"mode": "lockdown", "trusted": ["192.168.1.5"]})
        self.assertEqual((p.mode, p.allow_lan), ("lockdown", False))
        self.assertEqual(model.policy({"auto_block_minutes": 0}, p).auto_block_minutes, 1)
        with self.assertRaises(ValueError):
            model.policy({"mode": "aperto"})


class CompilerTests(unittest.TestCase):

    def test_monitor_and_off_only_remove_the_table(self):
        for mode in ("off", "monitor"):
            self.assertEqual(_compile(mode).splitlines(), ["table inet atena_guard", "delete table inet atena_guard"])

    def test_lockdown_denies_by_default_but_keeps_admin_access(self):
        script = _compile("lockdown", allow_lan=False, trusted=["aa:bb:cc:dd:ee:ff", "192.168.1.5"])
        self.assertIn("type filter hook input priority filter - 5; policy drop;", script)
        self.assertIn("tcp dport { 22, 80, 443, 8080 } accept", script)
        self.assertIn("elements = { aa:bb:cc:dd:ee:ff }", script)
        self.assertIn("ct state established,related accept", script)
        self.assertNotIn("ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16 } accept\n", script)

    def test_only_selected_devices_reach_a_service(self):
        script = _compile("lockdown", rules=[{"action": "accept", "protocol": "tcp", "ports": ["8123"],
                                               "sources": ["192.168.1.0/24", "aa:bb:cc:dd:ee:ff", "@ufficio"]}],
                          sets={"ufficio": ["10.1.0.0/16", "fd00::/8", "11:22:33:44:55:66"]})
        self.assertIn("ip saddr { 192.168.1.0/24 } meta l4proto tcp tcp dport { 8123 } counter accept", script)
        self.assertIn("ether saddr { aa:bb:cc:dd:ee:ff } meta l4proto tcp tcp dport { 8123 } counter accept", script)
        self.assertIn("ip6 saddr @ufficio_6 meta l4proto tcp", script)
        self.assertIn("ether saddr @ufficio_mac meta l4proto tcp", script)
        self.assertNotIn("ip saddr { 192.168.1.0/24 } ether saddr", script)

    def test_blocks_expire_and_carry_timeouts(self):
        blocks = [nft.Block(model.address("203.0.113.9"), NOW + 600), nft.Block(model.address("198.51.100.1"), NOW - 1),
                  nft.Block(model.address("2001:db8::66"), 0)]
        script = _compile(blocks=blocks)
        self.assertIn("203.0.113.9 timeout 600s", script)
        self.assertNotIn("198.51.100.1", script)
        self.assertIn("elements = { 2001:db8::66 }", script)

    def test_rules_follow_priority_and_skip_expired_ones(self):
        script = _compile(rules=[{"action": "drop", "priority": 50, "sources": ["1.1.1.1"], "comment": "secondo"},
                                 {"action": "reject", "priority": 10, "sources": ["2.2.2.2"], "comment": "primo"},
                                 {"action": "drop", "sources": ["3.3.3.3"], "expires": NOW - 5}])
        self.assertLess(script.index("primo"), script.index("secondo"))
        self.assertNotIn("3.3.3.3", script)

    def test_user_rules_come_before_lan_and_ping_fallbacks(self):
        script = _compile("lockdown", allow_lan=True, rules=[{"action": "drop", "sources": ["192.168.1.66"], "comment": "intruso"}])
        lan = script.index("ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16 } accept")
        self.assertLess(script.index("intruso"), lan)
        self.assertLess(script.index("@blocked_4"), script.index("tcp dport { 22, 80, 443, 8080 } accept"))
        self.assertNotIn("limit rate 20/second accept", _compile("protect"))

    def test_output_rules_use_the_output_interface(self):
        script = _compile(rules=[{"action": "drop", "direction": "output", "interface": "wg0", "destinations": ["8.8.8.8"]}])
        self.assertIn('oifname "wg0" ip daddr { 8.8.8.8 } counter drop', script)

    @unittest.skipUnless(shutil.which("nft") and hasattr(os, "geteuid") and os.geteuid() == 0, "serve nft come root")
    def test_scripts_are_accepted_by_nftables(self):
        script = _compile("lockdown", rules=[{"action": "limit", "protocol": "tcp", "ports": ["22"], "rate": "10/minute",
                                               "sources": ["@ufficio", "aa:bb:cc:dd:ee:ff"]},
                                              {"action": "reject", "direction": "output", "destinations": ["2001:db8::/32"]}],
                          sets={"ufficio": ["10.1.0.0/16"]}, blocks=[nft.Block(model.address("203.0.113.9"), NOW + 60)],
                          trusted=["192.168.1.5"])
        script = script.replace("delete table inet atena_guard\n", "", 1)
        with tempfile.NamedTemporaryFile("w", suffix=".nft", delete=False) as handle:
            handle.write(script)
        try:
            check = subprocess.run(["nft", "-c", "-f", handle.name], capture_output=True, text=True, timeout=20)
        finally:
            os.unlink(handle.name)
        self.assertEqual(check.returncode, 0, check.stderr + script)


if __name__ == "__main__":
    unittest.main()
