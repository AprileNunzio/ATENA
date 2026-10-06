from urllib.parse import quote

from features.cameras.netguard import HOST_RE, private_address

BRANDS = {
    "generic": {"label": "Generica (RTSP)", "port": 554, "path": "/stream{stream}", "main": "1", "sub": "2"},
    "hikvision": {"label": "Hikvision", "port": 554, "path": "/Streaming/Channels/{channel}0{stream}", "main": "1", "sub": "2"},
    "dahua": {"label": "Dahua / Amcrest / Imou", "port": 554, "path": "/cam/realmonitor?channel={channel}&subtype={stream}", "main": "0", "sub": "1"},
    "reolink": {"label": "Reolink", "port": 554, "path": "/h264Preview_{channel:02d}_{stream}", "main": "main", "sub": "sub"},
    "tapo": {"label": "TP-Link Tapo / Vigi", "port": 554, "path": "/stream{stream}", "main": "1", "sub": "2"},
    "foscam": {"label": "Foscam", "port": 554, "path": "/video{stream}", "main": "Main", "sub": "Sub"},
    "axis": {"label": "Axis", "port": 554, "path": "/axis-media/media.amp?camera={channel}", "main": "", "sub": ""},
    "ezviz": {"label": "Ezviz", "port": 554, "path": "/h264/ch{channel}/{stream}/av_stream", "main": "main", "sub": "sub"},
    "unifi": {"label": "Ubiquiti UniFi (RTSP)", "port": 7447, "path": "/{stream}", "main": "", "sub": ""},
    "wyze": {"label": "Wyze (firmware RTSP)", "port": 554, "path": "/live", "main": "", "sub": ""},
}


def listing() -> list[dict]:
    return [{"id": key, "label": b["label"], "port": b["port"]} for key, b in BRANDS.items()]


def build(brand: str, host: str, user: str = "", password: str = "", channel: int = 1, stream: str = "main", port: int = 0) -> str:
    spec = BRANDS.get(brand)
    if spec is None:
        raise ValueError("Marca sconosciuta")
    if not (private_address(host) or HOST_RE.match(host or "")):
        raise ValueError("Indirizzo non valido")
    channel = max(1, min(32, int(channel or 1)))
    kind = spec["sub"] if stream == "sub" else spec["main"]
    path = spec["path"].format(channel=channel, stream=kind)
    auth = f"{quote(user, safe='')}:{quote(password, safe='')}@" if user else ""
    number = int(port) if port else spec["port"]
    if not 1 <= number <= 65535:
        raise ValueError("Porta non valida")
    return f"rtsp://{auth}{host}:{number}{path}"
