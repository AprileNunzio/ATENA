import json
import logging
import queue
import ssl
import threading

from websockets.exceptions import ConnectionClosed, InvalidHandshake
from websockets.sync.client import connect

from connection import tls
from connection.client import Client, endpoint

log = logging.getLogger("atena.ear")
MAX_BACKOFF = 30.0


class EarStream(threading.Thread):
    def __init__(self, client: Client, on_event, on_status, on_security) -> None:
        super().__init__(daemon=True, name="ear")
        self.client, self.on_event, self.on_status, self.on_security = client, on_event, on_status, on_security
        self.audio: queue.Queue = queue.Queue(maxsize=200)
        self.control: queue.Queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.connected = False

    def send_audio(self, pcm: bytes) -> None:
        if self.connected and not self.audio.full():
            self.audio.put_nowait(pcm)

    def send(self, **message) -> None:
        if self.connected:
            self.control.put(message)

    def stop(self) -> None:
        self.stop_flag.set()

    def run(self) -> None:
        backoff = 2.0
        while not self.stop_flag.is_set():
            host, port = endpoint(self.client.server)
            try:
                with connect(f"wss://{host}:{port}/ws/ear", additional_headers=self.client.headers(), max_size=2 ** 22,
                             open_timeout=10, ssl=self.client.context(), server_hostname=host) as ws:
                    ws.send(json.dumps({"type": "client", "page": "desktop", "visible": "node"}))
                    self.connected, backoff = True, 2.0
                    self.on_status(True, "")
                    self._pump(ws)
            except ssl.SSLCertVerificationError as exc:
                self.on_security(str(tls.mismatch(exc)))
                return
            except tls.PinMismatch as exc:
                self.on_security(str(exc))
                return
            except (OSError, ssl.SSLError, InvalidHandshake, ConnectionClosed, TimeoutError) as exc:
                log.info("Ascolto remoto non disponibile: %s", exc)
                self.on_status(False, str(exc))
            self.connected = False
            self._drain()
            self.stop_flag.wait(backoff)
            backoff = min(backoff * 1.6, MAX_BACKOFF)

    def _drain(self) -> None:
        for pending in (self.audio, self.control):
            while not pending.empty():
                pending.get_nowait()

    def _pump(self, ws) -> None:
        while not self.stop_flag.is_set():
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
                    self._dispatch(message)

    def _dispatch(self, message: str) -> None:
        try:
            event = json.loads(message)
        except ValueError:
            log.warning("Messaggio non valido dal servizio di ascolto: %s", message[:120])
            return
        if isinstance(event, dict):
            self.on_event(event)
