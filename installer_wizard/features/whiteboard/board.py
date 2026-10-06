import base64
import json
import re
import time

from config import STATE_DIR

FILE = STATE_DIR / "whiteboard.json"
WIDTH, HEIGHT = 1600, 900
MAX_ITEMS = 3000
MAX_POINTS = 3000
MAX_TEXT = 300
MAX_SNAPSHOT = 2_000_000
COLUMNS = (60, 830)
COLUMN_WIDTH = 710
TOP, BOTTOM = 90, HEIGHT - 40
GAP = 18
MARKS = ("highlight", "underline", "wavy", "circle", "box", "strike")
CALLOUTS = ("info", "tip", "warning", "definition", "formula", "example")
CHARTS = ("bar", "line", "pie")
IMAGE_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$")
MAX_IMAGE = 1_500_000
MAX_IMAGES_PER_PAGE = 8
MAX_SERIES = 4
MAX_PLOT_POINTS = 400
MAX_TABLE = 12
MAX_CELL = 60
SHAPES = ("line", "arrow", "rect", "ellipse")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ATENA_INK = "#29e0ff"
USER_INK = "#f4f4f0"
ERROR_INK = "#ff4d6a"
NOTE_INK = "#ffd166"
PREVIOUS_SESSION = "sessione precedente"

def number(value, low: float, high: float, default: float = 0.0) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default

def color(value, default: str) -> str:
    return str(value) if COLOR.match(str(value or "")) else default

class Board:
    def __init__(self) -> None:
        self.pages: list[dict] = [{"items": [], "column": 0, "cursor": TOP, "snapshot": b"", "snapshot_at": 0.0}]
        self.page_index = 0
        self.items: list[dict] = self.pages[0]["items"]
        self.rev = 1
        self.counter = 0
        self.says = ""
        self.says_at = 0.0
        self.column = 0
        self.cursor = TOP
        self.snapshot: bytes = b""
        self.snapshot_at = 0.0
        self.ai_enabled = True
        self.load()

    def sync_page(self) -> None:
        p = self.pages[self.page_index]
        p["items"] = self.items
        p["column"] = self.column
        p["cursor"] = self.cursor
        p["snapshot"] = self.snapshot
        p["snapshot_at"] = self.snapshot_at

    def apply_page(self) -> None:
        p = self.pages[self.page_index]
        self.items = p["items"]
        self.column = p.get("column", 0)
        self.cursor = p.get("cursor", TOP)
        self.snapshot = p.get("snapshot", b"")
        self.snapshot_at = p.get("snapshot_at", 0.0)

    def load(self) -> None:
        try:
            data = json.loads(FILE.read_text(encoding="utf-8"))
            raw_pages = data.get("pages")
            if isinstance(raw_pages, list) and raw_pages:
                self.pages = []
                for p in raw_pages:
                    itms = [i for i in p.get("items", []) if isinstance(i, dict)][-MAX_ITEMS:]
                    self.pages.append({
                        "items": itms,
                        "column": int(p.get("column", 0)),
                        "cursor": float(p.get("cursor", TOP)),
                        "snapshot": b"",
                        "snapshot_at": 0.0
                    })
                self.page_index = max(0, min(len(self.pages) - 1, int(data.get("page_index", 0))))
            else:
                itms = [i for i in data.get("items", []) if isinstance(i, dict)][-MAX_ITEMS:]
                self.pages = [{
                    "items": itms,
                    "column": int(data.get("column", 0)),
                    "cursor": float(data.get("cursor", TOP)),
                    "snapshot": b"",
                    "snapshot_at": 0.0
                }]
                self.page_index = 0
            self.apply_page()
            all_ids = [int(i.get("id", 0)) for p in self.pages for i in p["items"]]
            self.counter = max(all_ids + [int(data.get("counter", 0)), 0])
            self.ai_enabled = bool(data.get("ai_enabled", True))
        except (OSError, ValueError, TypeError):
            self.pages = [{"items": [], "column": 0, "cursor": TOP, "snapshot": b"", "snapshot_at": 0.0}]
            self.page_index = 0
            self.apply_page()

    def save(self) -> None:
        self.sync_page()
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        payload = {
            "pages": [{
                "items": p["items"],
                "column": p.get("column", 0),
                "cursor": p.get("cursor", TOP)
            } for p in self.pages],
            "page_index": self.page_index,
            "counter": self.counter,
            "ai_enabled": self.ai_enabled
        }
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(FILE)

    def touch(self) -> None:
        self.rev += 1
        self.sync_page()
        self.save()

    def get_save_names(self) -> list[str]:
        return [p.stem.replace("whiteboard_", "", 1) for p in FILE.parent.glob("whiteboard_*.json")]

    def save_as(self, name: str) -> None:
        self.sync_page()
        self.save()
        safe = "".join(c for c in name if c.isalnum() or c in " -_")[:50].strip() or "unnamed"
        target = FILE.parent / f"whiteboard_{safe}.json"
        target.write_text(FILE.read_text(encoding="utf-8"), encoding="utf-8")

    def load_from(self, name: str) -> None:
        safe = "".join(c for c in name if c.isalnum() or c in " -_")[:50].strip() or "unnamed"
        target = FILE.parent / f"whiteboard_{safe}.json"
        if target.exists():
            FILE.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
            self.load()
            self.touch()

    def add_page(self) -> int:
        self.sync_page()
        self.pages.append({"items": [], "column": 0, "cursor": TOP, "snapshot": b"", "snapshot_at": 0.0})
        self.page_index = len(self.pages) - 1
        self.apply_page()
        self.touch()
        return self.page_index

    def switch_page(self, index: int) -> int:
        self.sync_page()
        if 0 <= index < len(self.pages):
            self.page_index = index
            self.apply_page()
            self.touch()
        return self.page_index

    def next_page(self) -> int:
        if self.page_index + 1 < len(self.pages):
            return self.switch_page(self.page_index + 1)
        return self.add_page()

    def prev_page(self) -> int:
        if self.page_index > 0:
            return self.switch_page(self.page_index - 1)
        return self.page_index

    def delete_page(self, index: int | None = None) -> int:
        if len(self.pages) <= 1:
            self.clear()
            return 0
        idx = self.page_index if index is None else index
        if 0 <= idx < len(self.pages):
            self.pages.pop(idx)
            self.page_index = max(0, min(len(self.pages) - 1, self.page_index))
            self.apply_page()
            self.touch()
        return self.page_index

    def toggle_ai(self, state: bool | None = None) -> bool:
        self.ai_enabled = not self.ai_enabled if state is None else bool(state)
        self.touch()
        return self.ai_enabled

    def add(self, item: dict) -> dict:
        if len(self.items) >= MAX_ITEMS:
            raise ValueError("la lavagna è piena: va cancellata o ripulita")
        self.counter += 1
        row = {**item, "id": self.counter, "at": time.time()}
        self.items.append(row)
        self.touch()
        return row

    def stroke(self, points, ink: str, width, erase: bool, by: str = "user") -> dict:
        clean = [[round(number(p[0], 0, WIDTH), 1), round(number(p[1], 0, HEIGHT), 1)] for p in (points or [])[:MAX_POINTS]
                 if isinstance(p, (list, tuple)) and len(p) == 2]
        if not clean:
            raise ValueError("tratto vuoto")
        return self.add({"type": "erase" if erase else "stroke", "by": by, "points": clean, "color": color(ink, USER_INK),
                         "width": number(width, 1, 60, 4)})

    def text(self, text: str, x=None, y=None, size=40, ink: str = ATENA_INK, by: str = "atena") -> dict:
        text = re.sub(r"\s+", " ", str(text)).strip()[:MAX_TEXT]
        if not text:
            raise ValueError("testo vuoto")
        size = number(size, 16, 140, 40)
        if x is None or y is None:
            x, y = self.place(size)
        return self.add({"type": "text", "by": by, "text": text, "x": number(x, 0, WIDTH), "y": number(y, 0, HEIGHT), "size": size,
                         "color": color(ink, ATENA_INK), "align": "left"})

    def underline(self, x1, y, x2, ink: str = ERROR_INK, width=4) -> dict:
        pts = []
        seg = max(6, int(abs(x2 - x1) / 10))
        for i in range(seg + 1):
            px = x1 + (x2 - x1) * (i / seg)
            py = y + (3.5 if i % 2 == 1 else -3.5)
            pts.append([round(px, 1), round(py, 1)])
        return self.stroke(pts, ink, width, False, by="atena")

    def place(self, size: float) -> tuple[float, float]:
        return self.reserve(size * 1.45, gap=0)

    def reserve(self, height: float, gap: float = GAP) -> tuple[float, float]:
        height = min(height, BOTTOM - TOP)
        boxes = self.occupied()
        while True:
            if self.cursor + height > BOTTOM:
                if self.column + 1 < len(COLUMNS):
                    self.column, self.cursor = self.column + 1, TOP
                else:
                    self.add_page()
                    boxes = []
                continue
            x, y = COLUMNS[self.column], self.cursor
            hits = [b for b in boxes if b[0] < x + COLUMN_WIDTH and b[2] > x and b[1] < y + height and b[3] > y]
            if not hits:
                self.cursor += height + gap
                return x, y
            self.cursor = max(max(b[3] for b in hits) + gap, self.cursor + 1)

    @staticmethod
    def wrap(text: str, size: float, width: float = COLUMN_WIDTH) -> list[str]:
        per_line = max(8, int(width / (size * 0.55)))
        lines, current = [], ""
        for word in re.sub(r"\s+", " ", str(text)).strip().split(" "):
            while len(word) > per_line:
                if current:
                    lines.append(current)
                    current = ""
                lines.append(word[:per_line])
                word = word[per_line:]
            candidate = f"{current} {word}".strip()
            if len(candidate) > per_line and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def paragraph(self, text: str, size: float = 40, ink: str = ATENA_INK) -> list[dict]:
        return [self.text(line, size=size, ink=ink) for line in self.wrap(text, size)[:12]]

    def mark(self, style: str, x1, y1, x2, y2, ink: str = NOTE_INK, width=4, target: int | None = None) -> dict:
        if style not in MARKS:
            raise ValueError("whiteboard.error.mark")
        if target is not None:
            found = next((i for i in self.items if i.get("id") == target), None)
            if found is None:
                raise ValueError("whiteboard.error.target")
            x1, y1, x2, y2 = self.bounds(found)
        return self.add({"type": "mark", "style": style, "by": "atena", "x1": number(x1, 0, WIDTH), "y1": number(y1, 0, HEIGHT),
                         "x2": number(x2, 0, WIDTH), "y2": number(y2, 0, HEIGHT), "color": color(ink, NOTE_INK), "width": number(width, 1, 20, 4)})

    @staticmethod
    def bounds(item: dict) -> tuple[float, float, float, float]:
        if item.get("type") == "text":
            return item["x"], item["y"], item["x"] + len(item["text"]) * item["size"] * 0.52, item["y"] + item["size"] * 1.1
        if "w" in item:
            return item["x"], item["y"], item["x"] + item["w"], item["y"] + item["h"]
        if "x1" in item:
            return item["x1"], item["y1"], item["x2"], item["y2"]
        xs = [p[0] for p in item.get("points", [[0, 0]])]
        ys = [p[1] for p in item.get("points", [[0, 0]])]
        return min(xs), min(ys), max(xs), max(ys)

    def callout(self, kind: str, title: str, text: str, x=None, y=None, w: float = COLUMN_WIDTH) -> dict:
        if kind not in CALLOUTS:
            raise ValueError("whiteboard.error.callout")
        size = 30
        lines = self.wrap(text, size, w - 40)[:8]
        height = 70 + len(lines) * size * 1.35
        if x is None or y is None:
            x, y = self.reserve(height)
        return self.add({"type": "callout", "kind": kind, "by": "atena", "title": str(title)[:80], "lines": lines, "size": size,
                         "x": number(x, 0, WIDTH), "y": number(y, 0, HEIGHT), "w": number(w, 200, WIDTH), "h": height})

    def image(self, data_uri: str, caption: str = "", x=None, y=None, w: float = 420, h: float = 300) -> dict:
        match = IMAGE_RE.match(str(data_uri or ""))
        if not match:
            raise ValueError("whiteboard.error.image")
        raw = base64.b64decode(match.group(2), validate=True)
        if len(raw) > MAX_IMAGE or not (raw.startswith(b"\x89PNG") or raw.startswith(b"\xff\xd8") or raw[8:12] == b"WEBP"):
            raise ValueError("whiteboard.error.image")
        if sum(1 for i in self.items if i.get("type") == "image") >= MAX_IMAGES_PER_PAGE:
            raise ValueError("whiteboard.error.too_many_images")
        w, h = number(w, 80, COLUMN_WIDTH), number(h, 60, BOTTOM - TOP - 40)
        if x is None or y is None:
            x, y = self.reserve(h + (36 if caption else 0))
        return self.add({"type": "image", "by": "atena", "src": data_uri, "caption": str(caption)[:120],
                         "x": number(x, 0, WIDTH), "y": number(y, 0, HEIGHT), "w": w, "h": h})

    def plot(self, series: list[dict], xmin: float, xmax: float, ymin: float, ymax: float, title: str = "",
             x=None, y=None, w: float = COLUMN_WIDTH, h: float = 420) -> dict:
        clean = []
        for s in series[:MAX_SERIES]:
            points = [[float(p[0]), None if p[1] is None else float(p[1])] for p in s.get("points", [])[:MAX_PLOT_POINTS]]
            clean.append({"label": str(s.get("label", ""))[:80], "color": color(s.get("color"), ATENA_INK), "points": points})
        if not clean or not xmin < xmax or not ymin < ymax:
            raise ValueError("whiteboard.error.plot")
        w, h = number(w, 200, COLUMN_WIDTH), number(h, 160, BOTTOM - TOP)
        if x is None or y is None:
            x, y = self.reserve(h)
        return self.add({"type": "plot", "by": "atena", "title": str(title)[:80], "series": clean, "xmin": xmin, "xmax": xmax,
                         "ymin": ymin, "ymax": ymax, "x": number(x, 0, WIDTH), "y": number(y, 0, HEIGHT), "w": w, "h": h})

    def chart(self, kind: str, labels: list, values: list, title: str = "", x=None, y=None, w: float = COLUMN_WIDTH, h: float = 380) -> dict:
        if kind not in CHARTS:
            raise ValueError("whiteboard.error.chart")
        try:
            vals = [float(v) for v in values][:MAX_TABLE]
        except (TypeError, ValueError):
            raise ValueError("whiteboard.error.chart")
        labs = [str(l)[:30] for l in labels][:len(vals)]
        if not vals or len(labs) != len(vals) or (kind == "pie" and (min(vals) < 0 or sum(vals) <= 0)):
            raise ValueError("whiteboard.error.chart")
        w, h = number(w, 200, COLUMN_WIDTH), number(h, 160, BOTTOM - TOP)
        if x is None or y is None:
            x, y = self.reserve(h)
        return self.add({"type": "chart", "kind": kind, "by": "atena", "title": str(title)[:80], "labels": labs, "values": vals,
                         "x": number(x, 0, WIDTH), "y": number(y, 0, HEIGHT), "w": w, "h": h})

    def formula(self, lines: list[str], label: str = "", size: float = 34, ink: str = ATENA_INK) -> dict:
        rows = [str(l)[:120] for l in lines][:14]
        if not rows:
            raise ValueError("whiteboard.error.formula")
        size = number(size, 18, 60, 34)
        x, y = self.reserve(size * 1.25 * len(rows) + (size if label else 0))
        return self.add({"type": "formula", "by": "atena", "lines": rows, "label": str(label)[:80], "size": size,
                         "x": x, "y": y, "color": color(ink, ATENA_INK)})

    def table(self, header: list, rows: list, title: str = "") -> dict:
        head = [str(c)[:MAX_CELL] for c in header][:8]
        body = [[str(c)[:MAX_CELL] for c in r][:len(head) or 8] for r in rows if isinstance(r, (list, tuple))][:MAX_TABLE]
        if not head and not body:
            raise ValueError("whiteboard.error.table")
        size = 26
        height = (len(body) + (1 if head else 0)) * size * 1.6 + (size * 1.4 if title else 0) + 10
        x, y = self.reserve(height)
        return self.add({"type": "table", "by": "atena", "title": str(title)[:80], "header": head, "rows": body, "size": size,
                         "x": x, "y": y, "w": COLUMN_WIDTH, "h": height})

    def shape(self, kind: str, x1, y1, x2, y2, ink: str = ATENA_INK, width=4, by: str = "atena") -> dict:
        if kind not in SHAPES:
            raise ValueError(f"figura sconosciuta: {', '.join(SHAPES)}")
        return self.add({"type": kind, "by": by, "x1": number(x1, 0, WIDTH), "y1": number(y1, 0, HEIGHT), "x2": number(x2, 0, WIDTH),
                         "y2": number(y2, 0, HEIGHT), "color": color(ink, ATENA_INK), "width": number(width, 1, 20, 4)})

    def say(self, text: str) -> None:
        self.says, self.says_at = str(text)[:240], time.time()
        self.touch()

    def undo(self, by: str = "user") -> bool:
        for index in range(len(self.items) - 1, -1, -1):
            if self.items[index].get("by") == by:
                self.items.pop(index)
                self.touch()
                return True
        return False

    def clear(self) -> int:
        count = len(self.items)
        self.items, self.column, self.cursor, self.says = [], 0, TOP, ""
        self.touch()
        return count

    def reset(self) -> None:
        if any(p.get("items") for p in self.pages) or self.items:
            self.save_as(PREVIOUS_SESSION)
        self.pages = [{"items": [], "column": 0, "cursor": TOP, "snapshot": b"", "snapshot_at": 0.0}]
        self.page_index = 0
        self.apply_page()
        self.snapshot, self.snapshot_at, self.says, self.says_at = b"", 0.0, "", 0.0
        self.touch()

    def occupied(self) -> list[tuple[float, float, float, float]]:
        boxes = []
        for item in self.items:
            if item.get("type") == "erase":
                continue
            try:
                boxes.append(self.bounds(item))
            except (KeyError, TypeError, ValueError):
                continue
        return boxes

    def free_spot(self, x: float, y: float, w: float, h: float) -> tuple[float, float] | None:
        x = number(x, 20, WIDTH - 60)
        w = min(w, WIDTH - 20 - x)
        boxes = self.occupied()
        for _ in range(60):
            if y + h > BOTTOM:
                return None
            hits = [b for b in boxes if b[0] < x + w and b[2] > x and b[1] < y + h and b[3] > y]
            if not hits:
                return x, y
            y = max(b[3] for b in hits) + 10
        return None

    def set_snapshot(self, jpeg: bytes) -> None:
        if not jpeg.startswith(b"\xff\xd8") or len(jpeg) > MAX_SNAPSHOT:
            raise ValueError("immagine non valida")
        self.snapshot, self.snapshot_at = jpeg, time.time()
        self.sync_page()

    def view(self) -> dict:
        return {
            "rev": self.rev,
            "width": WIDTH,
            "height": HEIGHT,
            "items": self.items,
            "page": self.page_index,
            "pages": len(self.pages),
            "ai_enabled": self.ai_enabled,
            "says": self.says,
            "says_at": self.says_at
        }

board = Board()
