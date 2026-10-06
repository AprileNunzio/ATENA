import asyncio
import ipaddress
import re
import socket
import time
import uuid

from features.cameras.cameras import cameras
from features.cameras.netguard import private_address, url_host

PORTS = (554, 8554)
GROUP = ("239.255.255.250", 3702)
XADDR = re.compile(r"https?://((?:\d{1,3}\.){3}\d{1,3})(?::\d+)?/", re.I)
NAME = re.compile(r"onvif://www\.onvif\.org/(?:name|hardware)/([^\s<]+)", re.I)
PROBE = ('<?xml version="1.0" encoding="UTF-8"?><e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
         'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
         'xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><e:Header><w:MessageID>uuid:{id}</w:MessageID>'
         '<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To><w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
         '</e:Header><e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body></e:Envelope>')
SEMAPHORE = 64
LIMIT = 256


def own_address() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def network_for(text_value: str = "") -> ipaddress.IPv4Network:
    if text_value:
        net = ipaddress.ip_network(text_value, strict=False)
    else:
        net = ipaddress.ip_network(f"{own_address()}/24", strict=False)
    if net.version != 4 or not net.is_private or net.num_addresses > LIMIT or net.is_loopback:
        raise ValueError("Rete non ammessa: usa una rete privata fino a 256 indirizzi (per esempio 192.168.1.0/24)")
    return net


def parse_onvif(payload: bytes) -> dict | None:
    body = payload.decode("utf-8", "replace")
    hosts = [m.group(1) for m in XADDR.finditer(body) if private_address(m.group(1))]
    if not hosts:
        return None
    name = NAME.search(body)
    return {"host": hosts[0], "onvif": True, "name": name.group(1).replace("%20", " ")[:40] if name else "", "ports": []}


def onvif(wait: float = 2.5) -> list[dict]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(0.5)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    found: dict[str, dict] = {}
    try:
        sock.sendto(PROBE.format(id=uuid.uuid4()).encode(), GROUP)
        end = time.time() + wait
        while time.time() < end:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                continue
            item = parse_onvif(data)
            if item:
                found.setdefault(item["host"], item)
    except OSError:
        return []
    finally:
        sock.close()
    return list(found.values())


async def port_open(host: str, port: int, gate: asyncio.Semaphore) -> bool:
    async with gate:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 0.5)
        except (OSError, asyncio.TimeoutError):
            return False
        writer.close()
        return True


async def scan(net: ipaddress.IPv4Network) -> dict[str, list[int]]:
    gate = asyncio.Semaphore(SEMAPHORE)
    hosts = [str(h) for h in net.hosts()]
    jobs = [(h, p) for h in hosts for p in PORTS]
    results = await asyncio.gather(*(port_open(h, p, gate) for h, p in jobs))
    open_ports: dict[str, list[int]] = {}
    for (host, port), ok in zip(jobs, results):
        if ok:
            open_ports.setdefault(host, []).append(port)
    return open_ports


def known_hosts() -> set[str]:
    return {url_host(c.get("url", "")) for c in cameras.items.values()}


async def find(network: str = "") -> dict:
    net = network_for(network)
    announced, open_ports = await asyncio.gather(asyncio.to_thread(onvif), scan(net))
    merged: dict[str, dict] = {item["host"]: item for item in announced}
    for host, ports in open_ports.items():
        merged.setdefault(host, {"host": host, "onvif": False, "name": "", "ports": []})["ports"] = ports
    known = known_hosts()
    rows = sorted(({**v, "known": v["host"] in known} for v in merged.values()), key=lambda r: tuple(int(p) for p in r["host"].split(".")) if r["host"].count(".") == 3 else (999,))
    return {"network": str(net), "found": rows}
