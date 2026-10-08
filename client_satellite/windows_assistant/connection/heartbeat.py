import logging
import threading

from connection import tls
from connection.client import Client, ServerError, Unauthorized

log = logging.getLogger("atena.link")
MIN_INTERVAL = 10.0


class Heartbeat(threading.Thread):
    def __init__(self, client: Client, report, on_reply, on_unauthorized, on_security) -> None:
        super().__init__(daemon=True, name="heartbeat")
        self.client, self.report = client, report
        self.on_reply, self.on_unauthorized, self.on_security = on_reply, on_unauthorized, on_security
        self.stop_flag = threading.Event()
        self.online = False

    def run(self) -> None:
        interval = 30.0
        while not self.stop_flag.is_set():
            try:
                reply = self.client.heartbeat(self.report())
            except Unauthorized:
                self.on_unauthorized()
                return
            except tls.PinMismatch as exc:
                self.on_security(str(exc))
                return
            except ServerError as exc:
                if self.online:
                    log.warning("ATENA non raggiungibile: %s", exc)
                self.online = False
            else:
                self.online = True
                interval = float(reply.get("heartbeat") or 30)
                self.on_reply(reply)
            self.stop_flag.wait(max(MIN_INTERVAL, interval))

    def stop(self) -> None:
        self.stop_flag.set()
