"""Collegamento con il server ATENA: API REST dei nodi e flusso del microfono verso /ws/ear."""
import json
import logging
import queue
import ssl
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger("atena.link")


class Unauthorized(Exception):
    pass


class ServerError(Exception):
    pass


def _ssl_context(url: str):
    if not url.startswith("https://"):
        return None
    ctx = ssl.create_default_context()
    # ATENA in LAN usa un certificato autogenerato
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class Link:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg

    @property
    def server(self) -> str:
        return self.cfg["server"]

    def _headers(self) -> dict:
        return {"X-Atena-Node": self.cfg["node_id"], "Authorization": f"Bearer {self.cfg['token']}"}

    def request(self, path: str, body: dict, auth: bool = True, timeout: float = 30.0, raw: bool = False):
        url = self.server + path
        headers = {"Content-Type": "application/json", **(self._headers() if auth else {})}
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context(url)) as res:
                data = res.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8", "replace")).get("detail", "")
            except (ValueError, AttributeError):
                pass
            if exc.code == 401:
                raise Unauthorized(detail or "Questo PC non è più autorizzato")
            raise ServerError(detail or f"Errore del server ({exc.code})")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ServerError(f"ATENA non raggiungibile: {getattr(exc, 'reason', exc)}")
        return data if raw else json.loads(data.decode("utf-8") or "{}")

    def pair(self, code: str, node_id: str, name: str) -> str:
        res = self.request("/api/nodes/pair", {"code": code, "id": node_id, "name": name, "type": "desktop"}, auth=False)
        return res["token"]

    def heartbeat(self, report: dict) -> dict:
        return self.request("/api/nodes/heartbeat", report, timeout=10)

    def assist(self, body: dict) -> dict:
        return self.request("/api/nodes/assist", body, timeout=300)

    def tts(self, text: str, lang: str | None) -> bytes:
        return self.request("/api/nodes/tts", {"text": text, "lang": lang or ""}, timeout=60, raw=True)


class EarStream(threading.Thread):
    """Invia l'audio del microfono (PCM 16 bit, 16 kHz, mono) al servizio di ascolto di ATENA e ne riceve gli
    eventi: parola di attivazione, trascrizioni, interruzioni."""

    def __init__(self, link: Link, on_event, on_status) -> None:
        super().__init__(daemon=True, name="ear")
        self.link, self.on_event, self.on_status = link, on_event, on_status
        self.audio: queue.Queue = queue.Queue(maxsize=200)
        self.control: queue.Queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.connected = False

    def send_audio(self, pcm: bytes) -> None:
        if self.connected:
            try:
                self.audio.put_nowait(pcm)
            except queue.Full:
                pass

    def send(self, **msg) -> None:
        if self.connected:
            self.control.put(msg)

    def stop(self) -> None:
        self.stop_flag.set()

    def run(self) -> None:
        from websockets.sync.client import connect
        backoff = 2.0
        while not self.stop_flag.is_set():
            url = self.link.server.replace("http://", "ws://", 1).replace("https://", "wss://", 1) + "/ws/ear"
            try:
                with connect(url, additional_headers=self.link._headers(), max_size=2 ** 22, open_timeout=10,
                             ssl=_ssl_context(self.link.server)) as ws:
                    ws.send(json.dumps({"type": "client", "page": "desktop", "visible": "node"}))
                    self.connected, backoff = True, 2.0
                    self.on_status(True, "")
                    self._pump(ws)
            except Exception as exc:  # rete, server spento, servizio di ascolto non attivo
                log.info("Ascolto remoto non disponibile: %s", exc)
                self.on_status(False, str(exc))
            self.connected = False
            self._drain()
            self.stop_flag.wait(backoff)
            backoff = min(backoff * 1.6, 30.0)

    def _drain(self) -> None:
        for q in (self.audio, self.control):
            while not q.empty():
                q.get_nowait()

    def _pump(self, ws) -> None:
        from websockets.exceptions import ConnectionClosed
        while not self.stop_flag.is_set():
            try:
                while not self.control.empty():
                    ws.send(json.dumps(self.control.get_nowait()))
                try:
                    ws.send(self.audio.get(timeout=0.05))
                except queue.Empty:
                    pass
                while True:
                    try:
                        message = ws.recv(timeout=0)
                    except TimeoutError:
                        break
                    if isinstance(message, str):
                        try:
                            self.on_event(json.loads(message))
                        except ValueError:
                            pass
            except ConnectionClosed:
                return


class Heartbeat(threading.Thread):
    def __init__(self, link: Link, report, on_commands, on_unauthorized) -> None:
        super().__init__(daemon=True, name="heartbeat")
        self.link, self.report, self.on_commands, self.on_unauthorized = link, report, on_commands, on_unauthorized
        self.stop_flag = threading.Event()
        self.online = False

    def run(self) -> None:
        interval = 30.0
        while not self.stop_flag.is_set():
            try:
                res = self.link.heartbeat(self.report())
                self.online = True
                interval = float(res.get("heartbeat") or 30)
                if res.get("commands"):
                    self.on_commands(res["commands"])
            except Unauthorized:
                self.on_unauthorized()
                return
            except ServerError:
                self.online = False
            self.stop_flag.wait(max(10.0, interval))

    def stop(self) -> None:
        self.stop_flag.set()


def wait_until(predicate, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False
