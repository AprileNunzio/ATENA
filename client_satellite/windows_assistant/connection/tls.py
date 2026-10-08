import hashlib
import ssl


class PinMismatch(ssl.SSLError):
    pass


def first_contact_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def pinned_context(ca_pem: str) -> ssl.SSLContext:
    if not ca_pem:
        raise PinMismatch("Nessuna autorità di certificazione di ATENA memorizzata: abbina di nuovo questo PC")
    ctx = ssl.create_default_context(cadata=ca_pem)
    ctx.check_hostname = False
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def fingerprint(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


def pem_fingerprint(pem: str) -> str:
    return fingerprint(ssl.PEM_cert_to_DER_cert(pem))


def short(value: str) -> str:
    head = value[:16].upper()
    return "-".join(head[i:i + 4] for i in range(0, len(head), 4))


def mismatch(exc: ssl.SSLError) -> PinMismatch:
    return PinMismatch(f"Il certificato presentato non è firmato dall'autorità di ATENA memorizzata ({exc.reason or exc})")
