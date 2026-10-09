import asyncio
import json
import unittest
from unittest import mock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from access import require_admin
from features.proxmox import api as proxmox_api
from features.proxmox import client as client_module
from features.proxmox.client import ProxmoxClient, ProxmoxError

NODES = [{"node": "pve", "status": "online", "cpu": 0.12, "maxcpu": 8, "mem": 4e9, "maxmem": 16e9, "uptime": 90000, "extra": "x"}]
GUESTS = [{"vmid": 101, "name": "nas", "node": "pve", "type": "lxc", "status": "running", "mem": 1e9, "maxmem": 2e9},
          {"vmid": 100, "name": "windows", "node": "pve", "type": "qemu", "status": "stopped"},
          {"vmid": 9000, "name": "tpl", "node": "pve", "type": "qemu", "status": "stopped", "template": 1}]


class FakeProxmox:
    def __init__(self):
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path.removeprefix("/api2/json")
        if path == "/access/ticket":
            return httpx.Response(200, json={"data": {"ticket": "T1", "CSRFPreventionToken": "C1"}})
        if path == "/nodes":
            return httpx.Response(200, json={"data": NODES})
        if path == "/cluster/resources":
            return httpx.Response(200, json={"data": GUESTS})
        if path.endswith("/status/start") or path.endswith("/snapshot"):
            return httpx.Response(200, json={"data": "UPID:pve:task"})
        return httpx.Response(404, json={})


def env(**values):
    base = {"PROXMOX_HOST": "192.168.1.5", "PROXMOX_USER": "root@pam", "PROXMOX_PASSWORD": "segreta"}
    base.update(values)
    return mock.patch.object(client_module, "env_get", side_effect=lambda k, d="": base.get(k, d))


class ClientTests(unittest.TestCase):

    def setUp(self):
        self.fake = FakeProxmox()
        self.client = ProxmoxClient(httpx.MockTransport(self.fake))

    def test_password_login_uses_ticket_and_csrf_only_for_writes(self):
        with env():
            overview = asyncio.run(self.client.overview())
            asyncio.run(self.client.power("pve", "qemu", 100, "start"))
        self.assertEqual([g["vmid"] for g in overview["guests"]], [100, 101])
        self.assertNotIn("extra", overview["nodes"][0])
        read = next(c for c in self.fake.calls if c.url.path.endswith("/nodes"))
        write = next(c for c in self.fake.calls if c.url.path.endswith("/status/start"))
        self.assertIn("PVEAuthCookie=T1", read.headers["cookie"])
        self.assertNotIn("csrfpreventiontoken", read.headers)
        self.assertEqual(write.headers["csrfpreventiontoken"], "C1")
        self.assertEqual(str(write.url), "https://192.168.1.5:8006/api2/json/nodes/pve/qemu/100/status/start")

    def test_api_token_is_sent_as_header(self):
        with env(PROXMOX_TOKEN_ID="root@pam!atena", PROXMOX_TOKEN_SECRET="abc-123"):
            asyncio.run(self.client.overview())
        self.assertFalse(any(c.url.path.endswith("/access/ticket") for c in self.fake.calls))
        self.assertEqual(self.fake.calls[0].headers["authorization"], "PVEAPIToken=root@pam!atena=abc-123")

    def test_invalid_requests_never_reach_proxmox(self):
        with env():
            for args in (("pve/../x", "qemu", 100, "start"), ("pve", "docker", 100, "start"), ("pve", "qemu", 100, "destroy"),
                         ("pve", "qemu", 1, "start")):
                with self.subTest(args=args), self.assertRaises(ProxmoxError):
                    asyncio.run(self.client.power(*args))
            with self.assertRaises(ProxmoxError):
                asyncio.run(self.client.snapshot("pve", "qemu", 100, "a b; rm"))
        self.assertEqual(self.fake.calls, [])
        with env(PROXMOX_HOST="evil.com/x?y"), self.assertRaises(ProxmoxError):
            asyncio.run(self.client.overview())


class ApiTests(unittest.TestCase):

    def setUp(self):
        app = FastAPI()
        app.include_router(proxmox_api.admin_routes)
        app.dependency_overrides[require_admin] = lambda: "nunzio"
        self.http = TestClient(app)
        self.fake = FakeProxmox()
        patcher = mock.patch.object(proxmox_api, "client", ProxmoxClient(httpx.MockTransport(self.fake)))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unconfigured_is_reported_not_crashing(self):
        with mock.patch.object(client_module, "env_get", return_value=""):
            self.assertEqual(self.http.get("/api/proxmox").json(), {"configured": False})

    def test_overview_power_and_snapshot(self):
        with env():
            body = self.http.get("/api/proxmox").json()
            self.assertEqual(len(body["guests"]), 2)
            self.assertEqual(self.http.post("/api/proxmox/pve/lxc/101/snapshot", json={"name": "prima-update"}).json(), {"task": "UPID:pve:task"})
            self.assertEqual(self.http.post("/api/proxmox/pve/qemu/100/start").status_code, 200)
            self.assertEqual(self.http.post("/api/proxmox/pve/qemu/100/destroy").status_code, 400)
        snapshot = next(c for c in self.fake.calls if c.url.path.endswith("/snapshot"))
        self.assertIn(b"snapname=prima-update", snapshot.content)

    def test_unreachable_host_is_an_error_message(self):
        def down(request):
            raise httpx.ConnectError("timeout")
        with env(), mock.patch.object(proxmox_api, "client", ProxmoxClient(httpx.MockTransport(down))):
            body = self.http.get("/api/proxmox").json()
        self.assertIn("non raggiungibile", body["error"])
        self.assertTrue(json.dumps(body))


if __name__ == "__main__":
    unittest.main()
