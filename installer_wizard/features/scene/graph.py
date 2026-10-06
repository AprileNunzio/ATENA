import json
import re
import sqlite3
import threading
import time
import uuid

NAME_RE = re.compile(r"^[\w .,'()+/-]{1,60}$", re.U)
SOURCE_RE = re.compile(r"^[a-z0-9_.:-]{1,64}$")
MAX_POINTS = 16
MAX_HISTORY = 50
MAX_ANCHORS = 200
MAX_ITEMS = 200
MAX_PROFILES = 30
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS anchors (id TEXT PRIMARY KEY, name TEXT, source TEXT, polygon TEXT, room TEXT, x REAL, y REAL, z REAL, entrance INTEGER)",
    "CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, name TEXT, labels TEXT, aliases TEXT)",
    "CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, name TEXT, aliases TEXT, requirements TEXT)",
    "CREATE TABLE IF NOT EXISTS sightings (label TEXT, source TEXT, at REAL, cx REAL, cy REAL, anchor TEXT, room TEXT, held INTEGER, holder TEXT, score REAL)",
    "CREATE INDEX IF NOT EXISTS sightings_label ON sightings(label, at)",
)


class SceneError(ValueError):
    pass


def _name(value) -> str:
    text = " ".join(str(value or "").split())
    if not NAME_RE.match(text):
        raise SceneError("scene.error.name")
    return text


def _names(values, limit: int = 12) -> list[str]:
    if not isinstance(values, list):
        raise SceneError("scene.error.list")
    return [_name(v) for v in values[:limit] if str(v or "").strip()]


def inside(point: tuple[float, float], polygon: list) -> bool:
    x, y = point
    hit = False
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % len(polygon)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1:
            hit = not hit
    return hit


def _polygon(value) -> list[list[float]]:
    if not isinstance(value, list) or not 3 <= len(value) <= MAX_POINTS:
        raise SceneError("scene.error.polygon")
    out = []
    for point in value:
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError, IndexError):
            raise SceneError("scene.error.polygon")
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise SceneError("scene.error.polygon")
        out.append([round(x, 4), round(y, 4)])
    return out


def _coordinate(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SceneError("scene.error.coordinate")
    if not -1000.0 <= number <= 1000.0:
        raise SceneError("scene.error.coordinate")
    return round(number, 3)


class SceneGraph:
    def __init__(self, path, clock=time.time) -> None:
        self.clock = clock
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        for statement in SCHEMA:
            self.db.execute(statement)
        self.db.commit()

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def _rows(self, sql: str, args=()) -> list[tuple]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def _write(self, sql: str, args=()) -> int:
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.rowcount

    def anchors(self) -> list[dict]:
        keys = ("id", "name", "source", "polygon", "room", "x", "y", "z", "entrance")
        out = []
        for row in self._rows("SELECT id, name, source, polygon, room, x, y, z, entrance FROM anchors ORDER BY name"):
            item = dict(zip(keys, row))
            item["polygon"], item["entrance"] = json.loads(item["polygon"]), bool(item["entrance"])
            out.append(item)
        return out

    def save_anchor(self, body: dict) -> dict:
        source = str(body.get("source") or "main")
        if not SOURCE_RE.match(source):
            raise SceneError("scene.error.source")
        anchor_id = str(body.get("id") or uuid.uuid4().hex[:10])
        if not re.match(r"^[a-f0-9]{10}$", anchor_id):
            raise SceneError("scene.error.id")
        if not body.get("id") and len(self.anchors()) >= MAX_ANCHORS:
            raise SceneError("scene.error.too_many")
        room = " ".join(str(body.get("room") or "").split())[:60]
        if room:
            _name(room)
        row = (anchor_id, _name(body.get("name")), source, json.dumps(_polygon(body.get("polygon"))), room,
               _coordinate(body.get("x")), _coordinate(body.get("y")), _coordinate(body.get("z")), int(bool(body.get("entrance"))))
        self._write("INSERT OR REPLACE INTO anchors VALUES (?,?,?,?,?,?,?,?,?)", row)
        return next(a for a in self.anchors() if a["id"] == anchor_id)

    def items(self) -> list[dict]:
        return [{"id": i, "name": n, "labels": json.loads(lb), "aliases": json.loads(al)}
                for i, n, lb, al in self._rows("SELECT id, name, labels, aliases FROM items ORDER BY name")]

    def save_item(self, body: dict) -> dict:
        item_id = str(body.get("id") or uuid.uuid4().hex[:10])
        if not re.match(r"^[a-f0-9]{10}$", item_id):
            raise SceneError("scene.error.id")
        if not body.get("id") and len(self.items()) >= MAX_ITEMS:
            raise SceneError("scene.error.too_many")
        labels = _names(body.get("labels") or [])
        if not labels:
            raise SceneError("scene.error.labels")
        self._write("INSERT OR REPLACE INTO items VALUES (?,?,?,?)", (item_id, _name(body.get("name")), json.dumps(labels),
                                                                     json.dumps(_names(body.get("aliases") or []))))
        return next(i for i in self.items() if i["id"] == item_id)

    def profiles(self) -> list[dict]:
        return [{"id": i, "name": n, "aliases": json.loads(al), "requirements": json.loads(rq)}
                for i, n, al, rq in self._rows("SELECT id, name, aliases, requirements FROM profiles ORDER BY name")]

    def save_profile(self, body: dict) -> dict:
        profile_id = str(body.get("id") or uuid.uuid4().hex[:10])
        if not re.match(r"^[a-f0-9]{10}$", profile_id):
            raise SceneError("scene.error.id")
        if not body.get("id") and len(self.profiles()) >= MAX_PROFILES:
            raise SceneError("scene.error.too_many")
        items = {i["id"] for i in self.items()}
        anchors = {a["id"] for a in self.anchors()}
        requirements = []
        for req in (body.get("requirements") or [])[:20]:
            if not isinstance(req, dict) or req.get("item") not in items:
                raise SceneError("scene.error.requirement")
            where = req.get("anchor") or ""
            if where and where not in anchors:
                raise SceneError("scene.error.requirement")
            max_age = max(1, min(7 * 24 * 60, int(req.get("max_age_min") or 720)))
            requirements.append({"item": req["item"], "anchor": where, "near_entrance": bool(req.get("near_entrance")), "max_age_min": max_age})
        if not requirements:
            raise SceneError("scene.error.requirement")
        self._write("INSERT OR REPLACE INTO profiles VALUES (?,?,?,?)", (profile_id, _name(body.get("name")),
                                                                         json.dumps(_names(body.get("aliases") or [])), json.dumps(requirements)))
        return next(p for p in self.profiles() if p["id"] == profile_id)

    def delete(self, kind: str, entry_id: str) -> bool:
        table = {"anchor": "anchors", "item": "items", "profile": "profiles"}.get(kind)
        if not table:
            raise SceneError("scene.error.kind")
        return self._write(f"DELETE FROM {table} WHERE id = ?", (entry_id,)) == 1

    def locate(self, source: str, cx: float, cy: float) -> dict | None:
        for anchor in self.anchors():
            if anchor["source"] == source and inside((cx, cy), anchor["polygon"]):
                return anchor
        return None

    def observe(self, source: str, objects: list[dict], frame: tuple[int, int], holder: str = "") -> int:
        width, height = frame
        if width <= 0 or height <= 0:
            return 0
        now, written = self.clock(), 0
        for obj in objects[:40]:
            try:
                x, y, w, h = (float(v) for v in obj["box"])
                label, score = str(obj["label"])[:40], float(obj.get("score", 0))
            except (KeyError, TypeError, ValueError):
                continue
            cx, cy = min(1.0, max(0.0, (x + w / 2) / width)), min(1.0, max(0.0, (y + h / 2) / height))
            anchor = self.locate(source, cx, cy)
            last = self._rows("SELECT at, anchor, held FROM sightings WHERE label = ? AND source = ? ORDER BY at DESC LIMIT 1", (label, source))
            held = bool(obj.get("held"))
            if last and now - last[0][0] < 30 and last[0][1] == (anchor or {}).get("id", "") and bool(last[0][2]) == held:
                continue
            self._write("INSERT INTO sightings VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (label, source, now, round(cx, 4), round(cy, 4), (anchor or {}).get("id", ""), (anchor or {}).get("room", ""),
                         int(held), holder[:60] if held else "", round(score, 3)))
            self._write("DELETE FROM sightings WHERE label = ? AND rowid NOT IN (SELECT rowid FROM sightings WHERE label = ? ORDER BY at DESC LIMIT ?)",
                        (label, label, MAX_HISTORY))
            written += 1
        return written

    def last_seen(self, labels: list[str]) -> dict | None:
        if not labels:
            return None
        marks = ",".join("?" * len(labels))
        rows = self._rows(f"SELECT label, source, at, cx, cy, anchor, room, held, holder, score FROM sightings WHERE label IN ({marks}) "
                          "ORDER BY at DESC LIMIT 1", tuple(labels))
        if not rows:
            return None
        keys = ("label", "source", "at", "cx", "cy", "anchor", "room", "held", "holder", "score")
        seen = dict(zip(keys, rows[0]))
        seen["held"] = bool(seen["held"])
        anchor = next((a for a in self.anchors() if a["id"] == seen["anchor"]), None)
        seen["anchor_name"] = anchor["name"] if anchor else ""
        seen["position"] = {k: anchor[k] for k in ("x", "y", "z")} if anchor and anchor["x"] is not None else None
        seen["entrance"] = bool(anchor and anchor["entrance"])
        return seen

    def readiness(self, profile: dict) -> dict:
        items = {i["id"]: i for i in self.items()}
        anchors = {a["id"]: a for a in self.anchors()}
        now = self.clock()
        checks = []
        for req in profile["requirements"]:
            item = items.get(req["item"])
            if item is None:
                continue
            seen = self.last_seen(item["labels"])
            if seen is None:
                status = "unknown"
            elif now - seen["at"] > req["max_age_min"] * 60:
                status = "stale"
            elif seen["held"]:
                status = "with_person"
            elif req["anchor"] and seen["anchor"] != req["anchor"]:
                status = "elsewhere"
            elif req["near_entrance"] and not seen["entrance"]:
                status = "elsewhere"
            else:
                status = "ok"
            checks.append({"item": item["name"], "status": status, "seen": seen,
                           "expected": anchors.get(req["anchor"], {}).get("name", "") if req["anchor"] else ""})
        return {"profile": profile["name"], "ready": bool(checks) and all(c["status"] in ("ok", "with_person") for c in checks),
                "checks": checks}

    def export(self) -> dict:
        rooms: dict[str, list] = {}
        for anchor in self.anchors():
            rooms.setdefault(anchor["room"] or "", []).append(anchor["id"])
        nodes = [{"id": f"room:{r}", "type": "room", "name": r} for r in rooms if r]
        edges = []
        for anchor in self.anchors():
            nodes.append({"id": f"anchor:{anchor['id']}", "type": "anchor", "name": anchor["name"],
                          "position": [anchor["x"], anchor["y"], anchor["z"]] if anchor["x"] is not None else None})
            if anchor["room"]:
                edges.append({"from": f"anchor:{anchor['id']}", "to": f"room:{anchor['room']}", "relation": "in"})
        for item in self.items():
            nodes.append({"id": f"item:{item['id']}", "type": "item", "name": item["name"]})
            seen = self.last_seen(item["labels"])
            if seen and seen["anchor"]:
                edges.append({"from": f"item:{item['id']}", "to": f"anchor:{seen['anchor']}", "relation": "on", "at": seen["at"]})
        return {"nodes": nodes, "edges": edges}
