import os
import shutil
import socket
import stat
import tempfile
import unittest
from unittest import mock

from sandbox_broker import native_egress
from sandbox_broker.egress import EgressProxy
from sandbox_broker.native_egress import NativeEgressProxy, open_egress_proxy, trusted_binary
from server.tests import test_sandbox_egress as base

TEST_BINARY = os.environ.get("ATENA_EGRESS_TEST_BIN", "")


def closed_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@unittest.skipUnless(TEST_BINARY and os.access(TEST_BINARY, os.X_OK), "atena-egress test build not available")
class NativeProxyBehaviourTest(base.ProxyBehaviourTest):
    def make_proxy(self, upstream, allowed, table=None, refused=False, max_bytes=16 * 1024 * 1024, port_range=(0, 0),
                   lifetime=10):
        port = closed_port() if refused or upstream is None else upstream.port
        hooks = {"resolve": table or base.DEFAULT_TABLE, "upstream": f"127.0.0.1:{port}"}
        return NativeEgressProxy(TEST_BINARY, "127.0.0.1", allowed, lifetime, max_bytes=max_bytes, port_range=port_range,
                                 hooks=hooks)

    def test_reports_kernel_sandbox_and_traffic(self):
        upstream = base.UpstreamServer()
        self.addCleanup(upstream.close)
        with self.make_proxy(upstream, ["api.example.com"]) as proxy:
            self.assertIn(proxy.sandbox, ("full", "partial", "none"))
            with socket.create_connection(("127.0.0.1", proxy.port), timeout=3) as client:
                client.sendall(b"CONNECT api.example.com:443 HTTP/1.1\r\n\r\n")
                client.recv(4096)
                client.sendall(b"ping")
                client.recv(4096)
        self.assertEqual(proxy.carried, 8)

    def test_invalid_configuration_is_refused(self):
        with self.assertRaises(OSError):
            NativeEgressProxy(TEST_BINARY, "127.0.0.1", ["localhost"], 5)

    def test_proxy_stops_at_its_lifetime(self):
        proxy = self.make_proxy(None, ["api.example.com"], lifetime=0.2)
        self.assertEqual(proxy._process.wait(timeout=5), 0)
        proxy.stop()
        self.assertEqual((proxy.carried, proxy.denied), (0, []))


class FactoryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.binary = os.path.join(self.dir, "atena-egress")

    def install(self, mode):
        with open(self.binary, "w") as handle:
            handle.write("#!/bin/sh\nexit 1\n")
        os.chmod(self.binary, mode)

    def open(self):
        proxy = open_egress_proxy(self.binary, "127.0.0.1", ["api.example.com"], 5, (0, 0))
        proxy.stop() if isinstance(proxy, NativeEgressProxy) else proxy.start().stop()
        return proxy

    def test_missing_binary_falls_back_to_python(self):
        self.assertIsInstance(self.open(), EgressProxy)

    def test_group_or_world_writable_binary_is_never_trusted(self):
        self.install(stat.S_IRWXU | stat.S_IWOTH)
        self.assertFalse(trusted_binary(self.binary))
        self.assertIsInstance(self.open(), EgressProxy)

    def test_broken_native_binary_falls_back_to_python(self):
        self.install(stat.S_IRWXU)
        self.assertTrue(trusted_binary(self.binary))
        self.assertIsInstance(self.open(), EgressProxy)

    def test_native_can_be_disabled(self):
        self.install(stat.S_IRWXU)
        with mock.patch.dict(os.environ, {"ATENA_NATIVE": "0"}), mock.patch.object(native_egress, "NativeEgressProxy") as native:
            self.assertIsInstance(self.open(), EgressProxy)
        native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
