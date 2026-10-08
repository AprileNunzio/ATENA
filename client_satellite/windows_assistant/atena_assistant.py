import ctypes
import hmac
import importlib
import re
import sys

importlib.import_module("customtkinter")

from app.errors import configure_logging, errors  # noqa: E402
from connection.client import Client, first_contact  # noqa: E402
from settings import autostart, store  # noqa: E402

MUTEX_NAME = "ATENA_Assistente_Windows"
ERROR_ALREADY_EXISTS = 183


def single_instance() -> bool:
    ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def verify(address: str) -> tuple[str, str]:
    return first_contact(store.normalize_server(address))


def pair(cfg: dict, address: str, code: str, name: str, start_with_windows: bool, fingerprint: str) -> None:
    server = store.normalize_server(address)
    if not server:
        raise ValueError("Scrivi l'indirizzo di ATENA")
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("Il codice deve avere 6 cifre")
    current, ca_pem = first_contact(server)
    if not hmac.compare_digest(current, fingerprint):
        raise ValueError("Il certificato di ATENA è cambiato durante l'abbinamento: premi di nuovo «Verifica»")
    name = name or cfg["name"]
    node_id = store.node_id_for(name)
    token = Client(server, node_id, "", ca_pem).pair(code, name)
    cfg.update(server=server, name=name, node_id=node_id, token=token, pin=fingerprint, ca=ca_pem)
    store.save(cfg)
    autostart.set_enabled(start_with_windows)


def main() -> None:
    configure_logging()
    errors.install()
    if not single_instance():
        ctypes.windll.user32.MessageBoxW(None, "ATENA è già in esecuzione: cerca la sfera luminosa nell'angolo dello schermo.",
                                         "ATENA", 0x40)
        return
    cfg = store.load()
    if not cfg["token"] or not cfg["ca"]:
        from ui.pairing_view import PairingWindow
        window = PairingWindow(cfg, verify, lambda *values: pair(cfg, *values))
        if not window.run():
            return
    from app.assistant import Assistant
    Assistant(cfg).start()


if __name__ == "__main__":
    sys.exit(main())
