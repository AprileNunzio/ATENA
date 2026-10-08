import ctypes
import ctypes.wintypes as wt


class ProtectionError(OSError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _call(data: bytes, protect: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(data, len(data))
    source, target = _Blob(len(data), buffer), _Blob()
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not function(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(target)):
        raise ProtectionError("Protezione dati di Windows (DPAPI) non riuscita")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)


def seal(data: bytes) -> bytes:
    return _call(data, True)


def unseal(data: bytes) -> bytes:
    return _call(data, False)
