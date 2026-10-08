import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from settings import paths

log = logging.getLogger("atena")


def configure_logging() -> None:
    paths.ensure()
    handler = RotatingFileHandler(paths.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


class GlobalErrors:
    def __init__(self) -> None:
        self.notify = None

    def install(self) -> None:
        sys.excepthook = self._main
        threading.excepthook = self._thread

    def attach(self, root, notify) -> None:
        self.notify = notify
        root.report_callback_exception = lambda kind, value, trace: self._report("interfaccia", (kind, value, trace))

    def _main(self, kind, value, trace) -> None:
        self._report("principale", (kind, value, trace))

    def _thread(self, args) -> None:
        self._report(args.thread.name if args.thread else "thread", (args.exc_type, args.exc_value, args.exc_traceback))

    def _report(self, where: str, exc_info) -> None:
        log.error("Errore non gestito (%s)", where, exc_info=exc_info)
        if self.notify:
            self.notify(f"⚠ Errore interno ({where}): {exc_info[1]}. Dettagli in {paths.LOG_FILE}")


errors = GlobalErrors()
