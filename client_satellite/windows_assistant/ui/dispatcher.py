import queue
import threading

POLL_MS = 30


class Dispatcher:
    def __init__(self, root) -> None:
        self.root = root
        self.jobs: queue.Queue = queue.Queue()
        self.ui_thread = threading.get_ident()
        self.root.after(POLL_MS, self._poll)

    def post(self, fn, *args) -> None:
        self.jobs.put((fn, args))

    def call(self, fn, *args):
        if threading.get_ident() == self.ui_thread:
            return fn(*args)
        done, box = threading.Event(), {}

        def run():
            try:
                box["value"] = fn(*args)
            except BaseException as exc:
                box["error"] = exc
            finally:
                done.set()

        self.post(run)
        done.wait()
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def _poll(self) -> None:
        self.root.after(POLL_MS, self._poll)
        while not self.jobs.empty():
            fn, args = self.jobs.get_nowait()
            fn(*args)
