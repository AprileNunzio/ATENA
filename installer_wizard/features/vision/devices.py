import re
from pathlib import Path

IR_FORMATS = {"GREY", "Y8", "Y10", "Y12", "Y16", "Y8I", "Y12I", "Z16"}
IR_NAME = re.compile(r"\b(ir|infra\s?red|infrared|depth|nir)\b", re.I)
HEADER_RE = re.compile(r"^(?P<name>.+?)\s+\((?P<bus>[^)]+)\):\s*$")
NODE_RE = re.compile(r"^\s+(/dev/video\d+)\s*$")
FORMAT_RE = re.compile(r"^\s*\[\d+\]:\s*'(?P<fourcc>[^']+)'")
SIZE_RE = re.compile(r"Size:\s*Discrete\s+(\d+)x(\d+)")
FPS_RE = re.compile(r"\(([\d.]+)\s*fps\)")
CAPS_RE = re.compile(r"^\s*(Video Capture(?: Multiplanar)?|Metadata Capture|Video Output|Streaming)\s*$", re.M)
CARD_RE = re.compile(r"Card type\s*:\s*(.+)")
BUS_RE = re.compile(r"Bus info\s*:\s*(.+)")
DRIVER_RE = re.compile(r"Driver name\s*:\s*(.+)")
USB_CLASS_VIDEO = "0e"


def parse_list(text: str) -> list[dict]:
    groups, current = [], None
    for line in text.splitlines():
        header = HEADER_RE.match(line)
        if header and not line.startswith((" ", "\t")):
            current = {"name": header["name"].strip(), "bus": header["bus"].strip(), "nodes": []}
            groups.append(current)
            continue
        node = NODE_RE.match(line)
        if node and current is not None:
            current["nodes"].append(node[1])
    return groups


def parse_formats(text: str) -> dict:
    formats: dict[str, dict] = {}
    fourcc, size = None, None
    for line in text.splitlines():
        m = FORMAT_RE.match(line)
        if m:
            fourcc, size = m["fourcc"].strip(), None
            formats.setdefault(fourcc, {})
            continue
        s = SIZE_RE.search(line)
        if s and fourcc:
            size = (int(s[1]), int(s[2]))
            formats[fourcc].setdefault(size, 0.0)
            continue
        f = FPS_RE.search(line)
        if f and fourcc and size:
            formats[fourcc][size] = max(formats[fourcc][size], float(f[1]))
    return formats


def parse_info(text: str) -> dict:
    section = text.split("Device Caps", 1)[1] if "Device Caps" in text else text
    caps = {m[1].replace(" Multiplanar", "") for m in CAPS_RE.finditer(section)}
    card, bus, driver = CARD_RE.search(text), BUS_RE.search(text), DRIVER_RE.search(text)
    return {"caps": caps, "card": card[1].strip() if card else "", "bus": bus[1].strip() if bus else "",
            "driver": driver[1].strip() if driver else ""}


def classify(info: dict, formats: dict, card: str = "") -> str:
    caps = info.get("caps", set())
    if "Metadata Capture" in caps and "Video Capture" not in caps:
        return "meta"
    if "Video Capture" not in caps and not formats:
        return "meta"
    fourccs = {f.upper() for f in formats}
    if fourccs and fourccs <= IR_FORMATS:
        return "ir"
    if fourccs & IR_FORMATS and not fourccs - IR_FORMATS - {"YUYV", "MJPG"} and IR_NAME.search(card or info.get("card", "")):
        return "ir"
    if IR_NAME.search(card or info.get("card", "")) and not (fourccs & {"MJPG", "H264", "NV12"}):
        return "ir"
    return "rgb"


def best_mode(formats: dict, prefer: tuple[str, ...], limit: tuple[int, int] | None = None) -> dict | None:
    best = None
    for fourcc in prefer:
        for key in formats:
            if key.upper() != fourcc:
                continue
            for (w, h), fps in formats[key].items():
                if limit and (w > limit[0] or h > limit[1]):
                    continue
                cand = {"fourcc": key, "width": w, "height": h, "fps": fps}
                if best is None or (w * h, fps) > (best["width"] * best["height"], best["fps"]):
                    best = cand
        if best:
            return best
    return best


def read_usb_ids(video: str, sysfs: Path = Path("/sys/class/video4linux")) -> dict:
    base = sysfs / Path(video).name / "device"
    out = {}
    for key, name in (("vendor", "idVendor"), ("product", "idProduct"), ("maker", "manufacturer"), ("model", "product")):
        for candidate in (base / ".." / name, base / name):
            try:
                out[key] = candidate.read_text(encoding="utf-8").strip()
                break
            except OSError:
                continue
    return out


def build(groups: list[dict], inspect, usb_ids=read_usb_ids) -> list[dict]:
    devices = []
    for g in groups:
        if not any(n.startswith("/dev/video") for n in g["nodes"]):
            continue
        nodes = {"rgb": [], "ir": [], "meta": []}
        raw, drivers = {}, []
        for path in g["nodes"]:
            info, formats = inspect(path)
            nodes[classify(info, formats, g["name"])].append(path)
            raw[path] = formats
            if info.get("driver"):
                drivers.append(info["driver"])
        if not nodes["rgb"] and not nodes["ir"]:
            continue
        ids = usb_ids(g["nodes"][0])
        rgb_formats = raw[nodes["rgb"][0]] if nodes["rgb"] else {}
        ir_formats = raw[nodes["ir"][0]] if nodes["ir"] else {}
        devices.append({
            "id": f"{ids.get('vendor', '----')}:{ids.get('product', '----')}@{g['bus']}",
            "name": g["name"], "bus": g["bus"], "vendor": ids.get("vendor", ""), "product": ids.get("product", ""),
            "maker": ids.get("maker", ""), "driver": drivers[0] if drivers else "",
            "rgb": nodes["rgb"][0] if nodes["rgb"] else None, "ir": nodes["ir"][0] if nodes["ir"] else None,
            "meta": nodes["meta"], "has_ir": bool(nodes["ir"]),
            "rgb_mode": best_mode(rgb_formats, ("MJPG", "YUYV", "NV12", "H264")),
            "ir_mode": best_mode(ir_formats, ("GREY", "Y8", "Y16", "Y10", "Y12", "YUYV", "MJPG")),
            "formats": {"rgb": sorted(rgb_formats), "ir": sorted(ir_formats)},
        })
    return devices


def choose(devices: list[dict], rgb_override: str = "auto", ir_override: str = "auto") -> dict:
    ranked = sorted(devices, key=lambda d: (d["has_ir"], (d["rgb_mode"] or {}).get("width", 0)), reverse=True)
    main = ranked[0] if ranked else None
    rgb = main["rgb"] if main else None
    ir = main["ir"] if main else None
    if rgb_override not in ("auto", "") and re.fullmatch(r"/dev/video\d+", rgb_override):
        rgb = rgb_override
    if ir_override == "off":
        ir = None
    elif ir_override not in ("auto", "") and re.fullmatch(r"/dev/video\d+", ir_override):
        ir = ir_override
    mode = next((d["rgb_mode"] for d in devices if d["rgb"] == rgb), None)
    ir_mode = next((d["ir_mode"] for d in devices if d["ir"] == ir), None)
    return {"device": main["id"] if main else None, "rgb": rgb, "ir": ir, "rgb_mode": mode, "ir_mode": ir_mode}


def signature(devices: list[dict]) -> str:
    return "|".join(sorted(f"{d['id']}:{d['rgb']}:{d['ir']}" for d in devices))
