import math
from dataclasses import dataclass, field

STRAIGHTNESS = 1.25
MIN_CHORD = 8.0
TALL = 14.0


@dataclass
class Stroke:
    points: list[list[float]]
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0

    def __post_init__(self) -> None:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        self.x0, self.y0, self.x1, self.y1 = min(xs), min(ys), max(xs), max(ys)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def chord(self) -> tuple[float, float]:
        (ax, ay), (bx, by) = self.points[0], self.points[-1]
        return bx - ax, by - ay

    def straight(self) -> bool:
        dx, dy = self.chord()
        chord = math.hypot(dx, dy)
        if chord < MIN_CHORD:
            return False
        length = sum(math.dist(a, b) for a, b in zip(self.points, self.points[1:]))
        return length <= chord * STRAIGHTNESS

    def direction(self) -> str:
        dx, dy = map(abs, self.chord())
        if dy <= dx * 0.5:
            return "h"
        if dx <= dy * 0.6:
            return "v"
        return "d"


@dataclass
class Glyph:
    strokes: list[Stroke] = field(default_factory=list)

    @property
    def x0(self) -> float:
        return min(s.x0 for s in self.strokes)

    @property
    def x1(self) -> float:
        return max(s.x1 for s in self.strokes)

    @property
    def y0(self) -> float:
        return min(s.y0 for s in self.strokes)

    @property
    def y1(self) -> float:
        return max(s.y1 for s in self.strokes)


def _cross(a: Stroke, b: Stroke) -> bool:
    (p1, p2), (p3, p4) = (a.points[0], a.points[-1]), (b.points[0], b.points[-1])

    def orient(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return d1 * d2 < 0 and d3 * d4 < 0


def lines(strokes: list[Stroke]) -> list[list[Stroke]]:
    tall = [s for s in strokes if s.height >= TALL]
    rows: list[list[Stroke]] = []
    for stroke in sorted(tall, key=lambda s: s.cy):
        row = next((r for r in rows if _overlaps_row(r, stroke)), None)
        if row is None:
            rows.append([stroke])
        else:
            row.append(stroke)
    for stroke in strokes:
        if stroke.height >= TALL:
            continue
        row = min(rows, key=lambda r: abs(_row_center(r) - stroke.cy), default=None)
        if row is not None and abs(_row_center(row) - stroke.cy) <= _row_height(row) * 0.75:
            row.append(stroke)
        else:
            rows.append([stroke])
    return rows


def _row_center(row: list[Stroke]) -> float:
    return (min(s.y0 for s in row) + max(s.y1 for s in row)) / 2


def _row_height(row: list[Stroke]) -> float:
    return max(TALL, max(s.y1 for s in row) - min(s.y0 for s in row))


def _overlaps_row(row: list[Stroke], stroke: Stroke) -> bool:
    top, bottom = min(s.y0 for s in row), max(s.y1 for s in row)
    overlap = min(bottom, stroke.y1) - max(top, stroke.y0)
    return overlap >= 0.4 * min(bottom - top, stroke.height)


def glyphs(row: list[Stroke]) -> list[Glyph]:
    out: list[Glyph] = []
    for stroke in sorted(row, key=lambda s: s.x0):
        last = out[-1] if out else None
        if last and _joins(last, stroke):
            last.strokes.append(stroke)
        else:
            out.append(Glyph([stroke]))
    return out


def _joins(glyph: Glyph, stroke: Stroke) -> bool:
    overlap = min(glyph.x1, stroke.x1) - max(glyph.x0, stroke.x0)
    narrow = max(4.0, min(glyph.x1 - glyph.x0, stroke.width))
    return overlap >= 0.3 * narrow or glyph.x0 <= stroke.cx <= glyph.x1


def operator(glyph: Glyph, line_height: float) -> str:
    parts = glyph.strokes
    if not all(s.straight() for s in parts):
        return ""
    kinds = sorted(s.direction() for s in parts)
    if len(parts) == 1:
        stroke = parts[0]
        if kinds == ["h"] and stroke.height <= line_height * 0.35:
            return "-"
        if kinds == ["d"] and stroke.chord()[0] * stroke.chord()[1] < 0:
            return "/"
        return ""
    if len(parts) == 2:
        a, b = parts
        if kinds == ["h", "h"] and (a.y1 < b.y0 or b.y1 < a.y0):
            return "="
        if kinds == ["h", "v"] and _cross(a, b):
            return "+"
        if kinds == ["d", "d"] and _cross(a, b):
            return "×"
    return ""
