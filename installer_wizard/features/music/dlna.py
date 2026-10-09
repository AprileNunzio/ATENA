import asyncio
import ipaddress
import logging
import re
import socket
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from xml.sax.saxutils import escape

import httpx

log = logging.getLogger("atena.music")
SSDP_ADDR = ("239.255.255.250", 1900)
RENDERER = "urn:schemas-upnp-org:device:MediaRenderer:1"
AVT = "urn:schemas-upnp-org:service:AVTransport:1"
RC = "urn:schemas-upnp-org:service:RenderingControl:1"
SEARCH = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
          f"ST: {RENDERER}\r\n\r\n").encode("ascii")
MAX_XML = 256 * 1024
STATES = {"PLAYING": "playing", "PAUSED_PLAYBACK": "paused", "STOPPED": "stopped", "TRANSITIONING": "loading", "NO_MEDIA_PRESENT": "stopped"}
TIME_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})(?:\.\d+)?$")


def private_host(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_link_local


def parse_ssdp(data: bytes) -> dict:
    headers = {}
    for line in data.decode("utf-8", errors="replace").split("\r\n")[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return headers


def seconds(text: str) -> float:
    match = TIME_RE.match((text or "").strip())
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + int(match.group(3)) if match else 0.0


def clock(value: float) -> str:
    value = max(0, int(value))
    return f"{value // 3600:d}:{value % 3600 // 60:02d}:{value % 60:02d}"


def find_services(xml_text: str, base: str) -> dict:
    root = ET.fromstring(xml_text)
    ns = {"d": "urn:schemas-upnp-org:device-1-0"}
    device = root.find("d:device", ns)
    if device is None:
        raise ValueError("descrizione senza dispositivo")
    out = {"name": (device.findtext("d:friendlyName", "", ns) or "Dispositivo").strip()[:60],
           "model": (device.findtext("d:modelName", "", ns) or "").strip()[:40]}
    for service in root.iter("{urn:schemas-upnp-org:device-1-0}service"):
        kind = service.findtext("d:serviceType", "", ns)
        control = service.findtext("d:controlURL", "", ns)
        if control and kind in (AVT, RC):
            out["avt" if kind == AVT else "rc"] = urljoin(base, control)
    return out


def discover_blocking(wait: float = 2.5) -> list[tuple[str, dict]]:
    found: dict = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(0.5)
    try:
        for _ in range(2):
            sock.sendto(SEARCH, SSDP_ADDR)
        end = time.time() + wait
        while time.time() < end:
            try:
                data, (ip, _) = sock.recvfrom(4096)
            except socket.timeout:
                continue
            headers = parse_ssdp(data)
            if headers.get("location") and private_host(ip):
                found[headers.get("usn", headers["location"])] = (ip, headers)
    except OSError as exc:
        log.info("Ricerca dispositivi DLNA non possibile: %s", exc)
    finally:
        sock.close()
    return list(found.values())


async def describe(ip: str, headers: dict) -> dict | None:
    location = headers["location"]
    parsed = urlparse(location)
    if parsed.scheme != "http" or parsed.hostname != ip or not private_host(ip):
        return None
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            reply = await client.get(location)
    except httpx.HTTPError:
        return None
    if reply.status_code != 200 or len(reply.content) > MAX_XML:
        return None
    try:
        services = find_services(reply.text, location)
    except (ET.ParseError, ValueError):
        return None
    if "avt" not in services:
        return None
    for key in ("avt", "rc"):
        if key in services and urlparse(services[key]).hostname != ip:
            services.pop(key)
    uuid = (headers.get("usn", "").split("::")[0] or location).replace("uuid:", "")
    return {"id": f"dlna:{re.sub(r'[^A-Za-z0-9-]', '', uuid)[:48]}", "kind": "dlna", "host": ip, **services}


async def discover() -> list[dict]:
    raw = await asyncio.to_thread(discover_blocking)
    described = await asyncio.gather(*(describe(ip, h) for ip, h in raw))
    return [d for d in described if d]


def envelope(service: str, action: str, arguments: dict) -> bytes:
    inner = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in arguments.items())
    return ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{service}"><InstanceID>0</InstanceID>{inner}</u:{action}></s:Body></s:Envelope>').encode("utf-8")


UPNP_AUDIO = "object.item.audioItem.musicTrack"
UPNP_VIDEO = "object.item.videoItem.videoBroadcast"


def didl(title: str, artist: str, album: str, url: str, art: str, mime: str) -> str:
    cover = f"<upnp:albumArtURI>{escape(art)}</upnp:albumArtURI>" if art else ""
    return ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"><item id="0" parentID="-1" restricted="1">'
            f"<dc:title>{escape(title)}</dc:title><dc:creator>{escape(artist)}</dc:creator><upnp:artist>{escape(artist)}</upnp:artist>"
            f"<upnp:album>{escape(album)}</upnp:album><upnp:class>{UPNP_VIDEO if mime.startswith('video') else UPNP_AUDIO}</upnp:class>{cover}"
            f'<res protocolInfo="http-get:*:{mime}:*">{escape(url)}</res></item></DIDL-Lite>')


async def call(device: dict, kind: str, action: str, arguments: dict | None = None) -> dict:
    url = device.get(kind)
    if not url:
        raise RuntimeError("Servizio non disponibile su questo dispositivo")
    service = AVT if kind == "avt" else RC
    headers = {"Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": f'"{service}#{action}"'}
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            reply = await client.post(url, content=envelope(service, action, arguments or {}), headers=headers)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Dispositivo non raggiungibile: {exc}")
    if reply.status_code >= 400:
        raise RuntimeError(f"Il dispositivo ha rifiutato «{action}» ({reply.status_code})")
    try:
        root = ET.fromstring(reply.text)
    except ET.ParseError:
        return {}
    return {el.tag.split("}")[-1]: (el.text or "") for el in root.iter() if el.text and el.tag.split("}")[-1][0].isupper()}


async def load(device: dict, url: str, meta: dict) -> None:
    metadata = didl(meta.get("title", ""), meta.get("artist", ""), meta.get("album", ""), url, meta.get("art", ""), meta.get("mime", "audio/mpeg"))
    await call(device, "avt", "SetAVTransportURI", {"CurrentURI": url, "CurrentURIMetaData": metadata})
    await call(device, "avt", "Play", {"Speed": 1})


async def status(device: dict) -> dict:
    info = await call(device, "avt", "GetTransportInfo")
    pos = await call(device, "avt", "GetPositionInfo")
    return {"state": STATES.get(info.get("CurrentTransportState", ""), "stopped"), "position": seconds(pos.get("RelTime", "")),
            "duration": seconds(pos.get("TrackDuration", ""))}


async def control(device: dict, action: str, value: float = 0.0) -> None:
    if action == "pause":
        await call(device, "avt", "Pause")
    elif action == "resume":
        await call(device, "avt", "Play", {"Speed": 1})
    elif action == "stop":
        await call(device, "avt", "Stop")
    elif action == "seek":
        await call(device, "avt", "Seek", {"Unit": "REL_TIME", "Target": clock(value)})
    elif action == "volume":
        await call(device, "rc", "SetVolume", {"Channel": "Master", "DesiredVolume": max(0, min(100, int(value * 100)))})
    else:
        raise ValueError("Comando non valido")
