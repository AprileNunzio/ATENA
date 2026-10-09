import logging
import threading

from connection.client import Client, ServerError, Unauthorized

log = logging.getLogger("atena.inbox")
POLL_TIMEOUT = 40.0
RETRY_AFTER = 10.0


class Inbox(threading.Thread):
    def __init__(self, client: Client, on_actions) -> None:
        super().__init__(daemon=True, name="inbox")
        self.client, self.on_actions = client, on_actions
        self.stop_flag = threading.Event()

    def run(self) -> None:
        while not self.stop_flag.is_set():
            try:
                reply = self.client.request("/api/nodes/inbox", {}, timeout=POLL_TIMEOUT)
            except Unauthorized:
                return
            except ServerError as exc:
                log.debug("Casella dei comandi non raggiungibile: %s", exc)
                self.stop_flag.wait(RETRY_AFTER)
                continue
            if reply.get("actions"):
                self.on_actions(reply["actions"])

    def stop(self) -> None:
        self.stop_flag.set()
