import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from access import require_admin
from sealed import SealedFile
from features.vpn import api as vpn_api
from features.vpn import profiles, runner, service as service_module, wireguard
from features.vpn import store as store_module
from features.vpn.service import service
from features.vpn.store import store
from tests.test_vpn_config import OVPN, WG


class VpnBase(unittest.TestCase):

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for target, name, value in ((store_module, "VPN_DIR", root), (store_module, "PROFILES_FILE", root / "profiles.json"),
                                    (store_module, "SECRETS", SealedFile(root / "vpn.vault", root / "vpn.key")),
                                    (service_module, "VPN_DIR", root), (service_module, "GUARD_FILE", root / "g.nft"),
                                    (runner, "CONF_DIR", root / "conf")):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        store.profiles, store.wanted = {}, {}
        service.state, service.failures, service.retry_at, service.endpoints = {}, {}, {}, {}
        self.calls: list = []

        async def up(p, secrets):
            self.calls.append(("up", p.id, sorted(secrets)))

        async def down(p):
            self.calls.append(("down", p.id))

        async def status(p):
            return {"connected": True}

        for name, fake in (("up", up), ("down", down), ("status", status)):
            patcher = mock.patch.object(runner, name, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        guard = mock.patch.object(service, "apply_guard", side_effect=lambda: asyncio.sleep(0))
        guard.start()
        self.addCleanup(guard.stop)


class ProfileBuildTests(VpnBase):

    def test_wireguard_import_keeps_split_from_allowed_ips(self):
        p, secrets = profiles.build({"name": "Ufficio", "kind": "wireguard", "import": WG.replace("0.0.0.0/0, ::/0", "10.20.0.0/16")})
        self.assertEqual((p.split.mode, p.split.networks), ("include", ["10.20.0.0/16"]))
        self.assertEqual(p.dns, ["10.8.0.1"])
        self.assertIn("private_key", secrets)

    def test_new_wireguard_client_generates_its_own_key(self):
        p, secrets = profiles.build({"name": "Casa", "kind": "wireguard", "settings": {
            "address": ["10.9.0.2/32"], "peer_public_key": wireguard.keypair()[1], "endpoint": "1.2.3.4:51820"}})
        self.assertEqual(len(profiles.public_key(secrets)), 44)
        self.assertNotIn("private_key", json.dumps(profiles.describe(p, secrets)))

    def test_openvpn_needs_credentials_when_the_file_asks(self):
        with self.assertRaises(ValueError):
            profiles.build({"name": "Lavoro", "kind": "openvpn", "import": OVPN})
        p, secrets = profiles.build({"name": "Lavoro", "kind": "openvpn", "import": OVPN,
                                     "secrets": {"username": "nunzio", "password": "segreta"}})
        self.assertEqual(secrets["password"], "segreta")

    def test_mesh_profiles_never_get_a_kill_switch(self):
        p, _ = profiles.build({"name": "Mesh", "kind": "tailscale", "kill_switch": True, "secrets": {"auth_key": "tskey-auth-abcdefghijklmnop"}})
        self.assertFalse(p.kill_switch)

    def test_secret_fields_reject_newlines(self):
        with self.assertRaises(ValueError):
            profiles.build({"name": "Lavoro", "kind": "openvpn", "import": OVPN, "secrets": {"username": "a\nscript-security 2", "password": "x"}})


class ServiceTests(VpnBase):

    def add(self, **extra):
        p, secrets = profiles.build({"name": "Casa", "kind": "zerotier", "settings": {"network_id": "8056c2e21c000001"}, **extra})
        store.put_secrets(p.id, secrets)
        store.profiles[p.id] = p
        return p

    def test_connect_is_remembered_and_restored_after_restart(self):
        p = self.add()
        asyncio.run(service.connect(p.id))
        store.profiles, store.wanted = {}, {}
        store.load()
        self.assertTrue(store.wanted[p.id])

    def test_dropped_tunnels_reconnect_with_backoff(self):
        p = self.add()
        store.wanted[p.id] = True

        async def broken(_):
            return {"connected": False}

        async def failing(profile, secrets):
            raise runner.VpnError("server irraggiungibile")

        with mock.patch.object(runner, "status", side_effect=broken), mock.patch.object(runner, "up", side_effect=failing):
            asyncio.run(service.check())
            first_retry = service.retry_at[p.id]
            asyncio.run(service.check())
        self.assertEqual(service.failures[p.id], 1)
        self.assertEqual(service.retry_at[p.id], first_retry)
        self.assertIn("irraggiungibile", service.state[p.id]["error"])

    def test_disconnect_wipes_config_files(self):
        p = self.add()
        conf = runner.CONF_DIR / f"{p.interface}.conf"
        conf.parent.mkdir(parents=True)
        conf.write_text("segreto", encoding="utf-8")
        asyncio.run(service.disconnect(p.id))
        self.assertFalse(conf.exists())
        self.assertFalse(store.wanted[p.id])


class ApiTests(VpnBase):

    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(vpn_api.admin_routes)
        app.dependency_overrides[require_admin] = lambda: "nunzio"
        self.client = TestClient(app)

    def test_server_devices_get_configs_and_secrets_stay_private(self):
        r = self.client.post("/api/vpn/profiles", json={"name": "Casa", "kind": "wireguard", "role": "server",
                                                        "settings": {"subnet": "10.66.0.0/24", "public_host": "casa.example.net"}})
        self.assertEqual(r.status_code, 200)
        pid = r.json()["created"]["id"]
        added = self.client.post(f"/api/vpn/profiles/{pid}/peers", json={"name": "Telefono"}).json()
        self.assertIn("Endpoint = casa.example.net:51820", added["config"])
        again = self.client.get(f"/api/vpn/profiles/{pid}/peers/{added['peer']['id']}").json()["config"]
        self.assertEqual(again, added["config"])
        overview = json.dumps(self.client.get("/api/vpn").json())
        self.assertNotIn("PrivateKey", overview)
        self.assertNotIn(store.secrets(pid)["private_key"], overview)
        self.assertEqual(self.client.delete(f"/api/vpn/profiles/{pid}/peers/{added['peer']['id']}").status_code, 200)
        self.assertEqual(store.get(pid).settings["peers"], [])

    def test_bad_imports_are_rejected(self):
        r = self.client.post("/api/vpn/profiles", json={"name": "X", "kind": "wireguard", "import": WG + "PostUp = id"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/api/vpn").json()["profiles"], [])

    def test_connect_disconnect_delete(self):
        pid = self.client.post("/api/vpn/profiles", json={"name": "ZT", "kind": "zerotier", "settings": {"network_id": "8056c2e21c000001"}}).json()["created"]["id"]
        self.assertTrue(self.client.post(f"/api/vpn/profiles/{pid}/connect").json()["status"]["connected"])
        self.client.post(f"/api/vpn/profiles/{pid}/disconnect")
        self.assertEqual(self.client.delete(f"/api/vpn/profiles/{pid}").status_code, 200)
        self.assertEqual(store.secrets(pid), {})
        self.assertEqual(self.client.post(f"/api/vpn/profiles/{pid}/connect").status_code, 404)


if __name__ == "__main__":
    unittest.main()
