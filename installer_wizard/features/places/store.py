import json
import logging
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field

from config import STATE_DIR

PLACES_FILE = STATE_DIR / "places" / "places.json"
NAME = re.compile(r"^[\w .,'()/-]{1,40}$", re.UNICODE)
KEY = re.compile(r"^(server|display:kiosk|mic:local|camera:main|node:[\w.-]{1,64}|camera:[\w.-]{1,64}|speaker:[\w.-]{1,64})$")
SENSES = ("sees", "hears", "shows", "speaks")
log = logging.getLogger("atena.places")


@dataclass
class Floor:
    name: str
    level: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class Room:
    name: str
    floor_id: str = ""
    aliases: list[str] = field(default_factory=list)
    ha_area: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class Placement:
    key: str
    room_id: str
    senses: list[str] = field(default_factory=list)


def _name(raw: str, label: str) -> str:
    text = " ".join(str(raw or "").split())
    if not NAME.match(text):
        raise ValueError(f"{label} non valido (massimo 40 caratteri)")
    return text


class PlacesStore:

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.floors: dict[str, Floor] = {}
        self.rooms: dict[str, Room] = {}
        self.placements: dict[str, Placement] = {}
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.error("Mappa di piani e stanze illeggibile: %s", exc)
            return
        with self.lock:
            self.floors = {f["id"]: Floor(**f) for f in data.get("floors") or []}
            self.rooms = {r["id"]: Room(**r) for r in data.get("rooms") or []}
            self.placements = {p["key"]: Placement(**p) for p in data.get("placements") or []}

    def save(self) -> None:
        with self.lock:
            PLACES_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = PLACES_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.export(), ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(PLACES_FILE)

    def export(self) -> dict:
        with self.lock:
            return {"floors": [asdict(f) for f in sorted(self.floors.values(), key=lambda f: (f.level, f.name))],
                    "rooms": [asdict(r) for r in sorted(self.rooms.values(), key=lambda r: r.name.lower())],
                    "placements": [asdict(p) for p in self.placements.values()]}

    def put_floor(self, data: dict, fid: str = "") -> Floor:
        floor = Floor(_name(data.get("name"), "nome del piano"), max(-5, min(int(data.get("level") or 0), 50)),
                      fid or uuid.uuid4().hex[:8])
        with self.lock:
            self.floors[floor.id] = floor
            self.save()
        return floor

    def delete_floor(self, fid: str) -> None:
        with self.lock:
            if fid not in self.floors:
                raise KeyError("piano sconosciuto")
            del self.floors[fid]
            for room in self.rooms.values():
                if room.floor_id == fid:
                    room.floor_id = ""
            self.save()

    def put_room(self, data: dict, rid: str = "") -> Room:
        floor_id = str(data.get("floor_id") or "")
        aliases = [_name(a, "nome alternativo") for a in (data.get("aliases") or [])[:10]]
        with self.lock:
            if floor_id and floor_id not in self.floors:
                raise ValueError("piano sconosciuto")
            room = Room(_name(data.get("name"), "nome della stanza"), floor_id, aliases,
                        str(data.get("ha_area") or "")[:64], rid or uuid.uuid4().hex[:8])
            clash = next((r for r in self.rooms.values() if r.id != room.id and r.name.lower() == room.name.lower()), None)
            if clash:
                raise ValueError(f"esiste già una stanza chiamata {room.name}")
            self.rooms[room.id] = room
            self.save()
        return room

    def delete_room(self, rid: str) -> None:
        with self.lock:
            if rid not in self.rooms:
                raise KeyError("stanza sconosciuta")
            del self.rooms[rid]
            for key in [k for k, p in self.placements.items() if p.room_id == rid]:
                del self.placements[key]
            self.save()

    def place(self, key: str, room_id: str, senses: list[str]) -> Placement | None:
        if not KEY.match(str(key or "")):
            raise ValueError("dispositivo non valido")
        clean = [s for s in SENSES if s in (senses or [])]
        with self.lock:
            if not room_id:
                self.placements.pop(key, None)
                self.save()
                return None
            if room_id not in self.rooms:
                raise ValueError("stanza sconosciuta")
            placement = Placement(key, room_id, clean)
            self.placements[key] = placement
            self.save()
            return placement

    def room_of(self, key: str) -> Room | None:
        with self.lock:
            placement = self.placements.get(key)
            return self.rooms.get(placement.room_id) if placement else None

    def import_areas(self, floors: dict, areas: dict) -> int:
        added = 0
        with self.lock:
            by_ha = {r.ha_area: r for r in self.rooms.values() if r.ha_area}
            floor_ids: dict[str, str] = {}
            for fid, f in (floors or {}).items():
                existing = next((x for x in self.floors.values() if x.name.lower() == str(f.get("name", "")).lower()), None)
                floor = existing or Floor(_name(f.get("name") or fid, "nome del piano"), int(f.get("level") or 0))
                self.floors[floor.id] = floor
                floor_ids[fid] = floor.id
            for aid, a in (areas or {}).items():
                if aid in by_ha:
                    continue
                name = _name(a.get("name") or aid, "nome della stanza")
                existing = next((r for r in self.rooms.values() if r.name.lower() == name.lower()), None)
                if existing:
                    existing.ha_area = aid
                    continue
                room = Room(name, floor_ids.get(a.get("floor_id") or "", ""), [], aid)
                self.rooms[room.id] = room
                added += 1
            self.save()
        return added


store = PlacesStore()
