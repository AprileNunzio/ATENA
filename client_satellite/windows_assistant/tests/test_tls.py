import datetime as dt
import ipaddress
import json
import ssl
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from connection import tls
from connection.client import Client, ServerError, first_contact


def _name(text: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, text)])


def authority(label: str):
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(_name(label)).issuer_name(_name(label)).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30)).add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .sign(key, hashes.SHA256()))
    return cert, key


def leaf(ca_cert, ca_key):
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(_name("Atena OS")).issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
            .sign(ca_key, hashes.SHA256()))
    return cert, key


def pem(cert) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode()


class FakeAtena:
    def __init__(self, folder: Path, served_ca, signing_ca) -> None:
        cert, key = leaf(*signing_ca)
        (folder / "server.pem").write_text(pem(cert), encoding="utf-8")
        (folder / "server.key").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                              serialization.NoEncryption()))
        ca_text = pem(served_ca[0])

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def _reply(self, status: int, body: bytes, kind: str = "application/json"):
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._reply(200, ca_text.encode(), "application/x-pem-file")

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self._reply(200, json.dumps({"heartbeat": 30, "commands": []}).encode())

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(folder / "server.pem", folder / "server.key")
        self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        self.url = f"https://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class PinningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.real_ca, self.evil_ca = authority("Atena OS Local CA"), authority("Intermediario")

    def tearDown(self):
        self.tmp.cleanup()

    def server(self, served, signing) -> FakeAtena:
        folder = Path(self.tmp.name) / served[0].subject.rfc4514_string()[:8].replace("=", "")
        folder.mkdir(exist_ok=True)
        fake = FakeAtena(folder, served, signing)
        self.addCleanup(fake.close)
        return fake

    def test_pairing_reads_and_checks_the_authority(self):
        atena = self.server(self.real_ca, self.real_ca)
        fingerprint, ca_pem = first_contact(atena.url)
        self.assertEqual(fingerprint, tls.pem_fingerprint(pem(self.real_ca[0])))
        reply = Client(atena.url, "pc-test", "token", ca_pem).heartbeat({})
        self.assertEqual(reply["heartbeat"], 30)

    def test_a_server_lying_about_its_authority_is_blocked_at_pairing(self):
        impostor = self.server(self.real_ca, self.evil_ca)
        with self.assertRaises(ServerError):
            first_contact(impostor.url)

    def test_after_pairing_a_different_authority_is_a_security_alert(self):
        impostor = self.server(self.evil_ca, self.evil_ca)
        with self.assertRaises(tls.PinMismatch):
            Client(impostor.url, "pc-test", "token", pem(self.real_ca[0])).heartbeat({})

    def test_plain_http_is_refused(self):
        with self.assertRaises(ServerError):
            Client("http://127.0.0.1:80", "pc", "t", pem(self.real_ca[0])).heartbeat({})


if __name__ == "__main__":
    unittest.main()
