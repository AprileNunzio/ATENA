import asyncio
import logging
import re

from features.cameras import live, options
from features.vision import webcams as cams

log = logging.getLogger("atena.cameras")
LINE = re.compile(r"^\s*([a-z0-9_]+)\s+0x[0-9a-f]+\s+\((int|bool|menu|button|intmenu)\)\s*:\s*(.*)$")
MENU = re.compile(r"^\s+(-?\d+):\s+(.+)$")
FIELD = re.compile(r"(min|max|step|default|value)=(-?\d+)")
SKIP = {"button"}
NODE_RE = re.compile(r"^/dev/video\d{1,3}$")


def parse(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in text.splitlines():
        found = LINE.match(line)
        if found:
            if found.group(2) in SKIP:
                rows.append(None)
                continue
            fields = {k: int(v) for k, v in FIELD.findall(found.group(3))}
            rows.append({"name": found.group(1), "type": found.group(2), "min": fields.get("min", 0), "max": fields.get("max", 1),
                         "step": fields.get("step", 1) or 1, "default": fields.get("default", 0), "value": fields.get("value", 0),
                         "inactive": "inactive" in found.group(3), "menu": []})
            continue
        item = MENU.match(line)
        if item and rows and rows[-1] is not None:
            rows[-1]["menu"].append({"value": int(item.group(1)), "label": item.group(2).strip()})
    return [r for r in rows if r]


def nodes() -> dict[str, str]:
    found = {}
    for device in cams.webcams.state.get("devices", []):
        for key in ("rgb", "ir"):
            if device.get(key):
                found[device[key]] = device["id"]
    return found


def node_of(source: dict) -> str:
    node = source.get("node") or ""
    if not NODE_RE.match(node) or node not in nodes():
        raise ValueError("Questa sorgente non è una webcam locale con controlli")
    return node


def read(node: str) -> list[dict]:
    return parse(cams.run_v4l(["-d", node, "--list-ctrls-menus"]))


def check(row: dict, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Valore non valido")
    if not row["min"] <= value <= row["max"]:
        raise ValueError(f"{row['name']} deve essere tra {row['min']} e {row['max']}")
    if row["type"] == "menu" and value not in {m["value"] for m in row["menu"]}:
        raise ValueError("Voce di menu non valida")
    return value


def write(node: str, name: str, value: int) -> None:
    cams.run_v4l(["-d", node, "--set-ctrl", f"{name}={value}"])


def apply(node: str, name: str, value) -> dict:
    row = next((r for r in read(node) if r["name"] == name), None)
    if row is None:
        raise ValueError("Controllo sconosciuto")
    write(node, name, check(row, value))
    return {**row, "value": value}


def reset(node: str) -> int:
    count = 0
    for row in read(node):
        if row["type"] != "menu" and row["inactive"]:
            continue
        write(node, row["name"], row["default"])
        count += 1
    return count


async def restore() -> None:
    saved = options.read()
    present = nodes()
    for source in cams.webcams.state.get("devices", []):
        sid = live.local_id(source)
        wanted = (saved.get(sid) or {}).get("controls") or {}
        node = source.get("rgb")
        if wanted and node in present:
            for name, value in wanted.items():
                try:
                    await asyncio.to_thread(apply, node, name, value)
                except (ValueError, OSError):
                    continue


async def run() -> None:
    last = ""
    while True:
        sig = ",".join(sorted(f"{d['id']}:{d.get('rgb')}" for d in cams.webcams.state.get("devices", [])))
        if sig and sig != last:
            last = sig
            try:
                await restore()
            except Exception:
                log.exception("Ripristino dei controlli webcam non riuscito")
        await asyncio.sleep(20)
