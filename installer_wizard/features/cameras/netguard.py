import ipaddress
import re
import socket
from urllib.parse import urlsplit

HOST_RE = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")


def private_address(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%")[0])
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def private_host(host: str) -> bool:
    if not host or not HOST_RE.match(host) and not private_address(host):
        return False
    try:
        found = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(found) and all(private_address(a) for a in found)


def url_host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def lan_url(url: str) -> bool:
    return urlsplit(url).scheme.lower() in ("rtsp", "rtsps", "http", "https") and private_host(url_host(url))


def redact(text_value: str, url: str = "") -> str:
    out = text_value.replace(url, "***") if url else text_value
    return re.sub(r"(://)[^/@\s]+@", r"\1***@", out)
