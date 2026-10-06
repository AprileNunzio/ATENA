from contextvars import ContextVar

device: ContextVar[str] = ContextVar("atena_device", default="kiosk")
voice: ContextVar[str] = ContextVar("atena_voice", default="")
TRUSTED = ("admin", "remote")


def trusted() -> bool:
    return device.get() in TRUSTED
