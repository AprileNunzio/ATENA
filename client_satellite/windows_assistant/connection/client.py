import http.client
import json
import logging
import ssl
from urllib.parse import urlsplit

from connection import tls

log = logging.getLogger("atena.link")
CA_PATH = "/atena-ca.crt"
CA_LIMIT = 65536


class Unauthorized(Exception):
    pass


class ServerError(Exception):
    pass


def endpoint(server: str) -> tuple[str, int]:
    parts = urlsplit(server)
    if parts.scheme != "https" or not parts.hostname:
        raise ServerError("ATENA si raggiunge solo in HTTPS")
    return parts.hostname, parts.port or 443


def _fetch_ca(host: str, port: int, timeout: float) -> str:
    conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=tls.first_contact_context())
    try:
        conn.request("GET", CA_PATH)
        response = conn.getresponse()
        body = response.read(CA_LIMIT)
    finally:
        conn.close()
    if response.status != 200:
        raise ServerError(f"ATENA non ha fornito il suo certificato di autorità (errore {response.status})")
    pem = body.decode("ascii", "replace")
    if "BEGIN CERTIFICATE" not in pem:
        raise ServerError("Il certificato di autorità ricevuto non è valido")
    return pem


def first_contact(server: str, timeout: float = 10) -> tuple[str, str]:
    host, port = endpoint(server)
    try:
        pem = _fetch_ca(host, port, timeout)
        probe = http.client.HTTPSConnection(host, port, timeout=timeout, context=tls.pinned_context(pem))
        try:
            probe.connect()
        finally:
            probe.close()
    except ssl.SSLCertVerificationError as exc:
        raise ServerError("Il certificato del server non è firmato dall'autorità che dichiara: possibile intermediario "
                          "in rete, abbinamento bloccato") from exc
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise ServerError(f"ATENA non raggiungibile in HTTPS su {host}:{port}: {exc}") from exc
    return tls.pem_fingerprint(pem), pem


class Client:
    def __init__(self, server: str, node_id: str, token: str, ca_pem: str) -> None:
        self.server, self.node_id, self.token, self.ca_pem = server, node_id, token, ca_pem

    def headers(self) -> dict:
        return {"X-Atena-Node": self.node_id, "Authorization": f"Bearer {self.token}"}

    def context(self) -> ssl.SSLContext:
        return tls.pinned_context(self.ca_pem)

    def request(self, path: str, body: dict, auth: bool = True, timeout: float = 30.0, raw: bool = False):
        host, port = endpoint(self.server)
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=self.context())
        try:
            conn.request("POST", path, json.dumps(body).encode("utf-8"),
                         {"Content-Type": "application/json", **(self.headers() if auth else {})})
            response = conn.getresponse()
            data = response.read()
        except ssl.SSLCertVerificationError as exc:
            raise tls.mismatch(exc) from exc
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise ServerError(f"ATENA non raggiungibile: {exc}") from exc
        finally:
            conn.close()
        if response.status == 401:
            raise Unauthorized(self._detail(data) or "Questo PC non è più autorizzato")
        if response.status >= 400:
            raise ServerError(self._detail(data) or f"Errore del server ({response.status})")
        return data if raw else json.loads(data.decode("utf-8") or "{}")

    @staticmethod
    def _detail(data: bytes) -> str:
        try:
            return str(json.loads(data.decode("utf-8", "replace")).get("detail", ""))
        except (ValueError, AttributeError):
            return ""

    def pair(self, code: str, name: str) -> str:
        res = self.request("/api/nodes/pair", {"code": code, "id": self.node_id, "name": name, "type": "desktop"}, auth=False)
        return res["token"]

    def heartbeat(self, report: dict) -> dict:
        return self.request("/api/nodes/heartbeat", report, timeout=10)

    def assist(self, body: dict) -> dict:
        return self.request("/api/nodes/assist", body, timeout=300)

    def tts(self, text: str, lang: str | None) -> bytes:
        return self.request("/api/nodes/tts", {"text": text, "lang": lang or ""}, timeout=60, raw=True)

    def download(self, path: str, body: dict, timeout: float = 300) -> bytes:
        return self.request(path, body, timeout=timeout, raw=True)
