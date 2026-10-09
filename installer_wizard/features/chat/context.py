from contextvars import ContextVar

device: ContextVar[str] = ContextVar("atena_device", default="kiosk")
voice: ContextVar[str] = ContextVar("atena_voice", default="")
TRUSTED = ("admin", "remote")


def trusted() -> bool:
    return device.get() in TRUSTED


def session_key() -> str:
    return f"{device.get()}|{voice.get()}"
