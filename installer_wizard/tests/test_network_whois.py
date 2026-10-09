import asyncio
import json
import time
import unittest
from unittest import mock

from features.firewall import analyst
from features.firewall.events import Monitor
from features.network import tools, whois
from features.network.explorer import explorer

DEVICES = {
    "aa:bb": {"key": "aa:bb", "ip": "192.168.1.5", "mac": "aa:bb", "name": "iPhone di Nunzio", "type": "phone",
              "room": "Studio", "owner": "Nunzio", "trusted": True, "online": True},
    "cc:dd": {"key": "cc:dd", "ip": "192.168.1.9", "mac": "cc:dd", "name": "", "hostname": "", "vendor": "Espressif",
              "type": "unknown", "trusted": False, "online": True},
}


class WhoisTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(explorer, "devices", dict(DEVICES))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_known_unknown_and_internet_addresses(self):
        self.assertEqual(whois.describe("192.168.1.5"), "192.168.1.5 (iPhone di Nunzio)")
        self.assertTrue(whois.who("AA:BB")["trusted"])
        self.assertEqual(whois.who("192.168.1.77")["label"], "dispositivo sconosciuto")
        self.assertEqual(whois.who("8.8.8.8")["label"], "Internet")
        self.assertIsNone(whois.who("not-an-ip"))
        self.assertEqual(whois.describe("not-an-ip"), "not-an-ip")

    def test_firewall_alerts_carry_names(self):
        monitor = Monitor()
        line = json.dumps({"type": "alert", "kind": "port_scan", "severity": "medium", "src": "192.168.1.9",
                           "dst": "192.168.1.5", "detail": "porte 1-1000"})
        with mock.patch("features.firewall.events.self_inflicted", return_value=False):
            asyncio.run(monitor.handle(line))
        alert = monitor.alerts[-1]
        self.assertEqual(alert["dst_who"], "iPhone di Nunzio")
        self.assertIn("Espressif", alert["who"])

    def test_network_view_and_analyst_digest(self):
        alerts = [{"src": "192.168.1.9", "dst": "1.1.1.1", "kind": "port_scan", "severity": "high", "detail": "x",
                   "at": time.time()}]
        view = whois.firewall_view(alerts, {"192.168.1.5": object()})
        self.assertEqual(view["cc:dd"]["alerts_24h"], 1)
        self.assertTrue(view["aa:bb"]["blocked"])
        devices = analyst.digest(alerts, {})["devices"]
        self.assertFalse(devices["192.168.1.9"]["trusted"])
        self.assertEqual(devices["1.1.1.1"]["name"], "Internet")

    def test_agent_tool(self):
        text = asyncio.run(tools.who_is("192.168.1.5"))
        self.assertIn("iPhone di Nunzio", text)
        self.assertIn("stanza Studio", text)


if __name__ == "__main__":
    unittest.main()
