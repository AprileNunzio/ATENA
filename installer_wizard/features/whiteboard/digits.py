import math
from functools import lru_cache

POINTS = 32
MAX_DISTANCE = 0.9
ASPECT_WEIGHT = 0.03
ORDER_WEIGHT = 0.6

Path = list[tuple[float, float]]


def _ellipse(cx: float, cy: float, rx: float, ry: float, start: float, turns: float = 1.0, steps: int = 24) -> Path:
    return [(cx + rx * math.sin(start + turns * 2 * math.pi * i / steps), cy - ry * math.cos(start + turns * 2 * math.pi * i / steps))
            for i in range(steps + 1)]


def _eight() -> Path:
    top = _ellipse(0.5, 0.25, 0.3, 0.25, math.pi, -1.0)
    bottom = _ellipse(0.5, 0.75, 0.35, 0.25, 0.0, 1.0)
    return top[:13] + bottom + top[13:]


TEMPLATES: dict[str, list[list[Path]]] = {
    "0": [[_ellipse(0.5, 0.5, 0.4, 0.5, 0.0, -1.0)], [_ellipse(0.5, 0.5, 0.35, 0.5, 0.0, 1.0)]],
    "1": [[[(0.5, 0.0), (0.5, 1.0)]], [[(0.25, 0.25), (0.55, 0.0), (0.55, 1.0)]]],
    "2": [[[(0.1, 0.25), (0.3, 0.02), (0.7, 0.02), (0.88, 0.25), (0.75, 0.5), (0.1, 1.0), (0.9, 1.0)]],
          [[(0.15, 0.2), (0.5, 0.0), (0.85, 0.2), (0.6, 0.55), (0.1, 1.0), (0.35, 0.9), (0.9, 0.95)]]],
    "3": [[[(0.1, 0.1), (0.5, 0.0), (0.85, 0.2), (0.45, 0.48), (0.9, 0.72), (0.5, 1.0), (0.1, 0.9)]],
          [[(0.15, 0.05), (0.85, 0.05), (0.4, 0.45), (0.85, 0.65), (0.6, 1.0), (0.1, 0.9)]]],
    "4": [[[(0.6, 0.0), (0.05, 0.65), (0.9, 0.65)], [(0.65, 0.3), (0.65, 1.0)]],
          [[(0.15, 0.0), (0.1, 0.55), (0.9, 0.55)], [(0.7, 0.0), (0.7, 1.0)]]],
    "5": [[[(0.85, 0.0), (0.2, 0.0), (0.15, 0.45), (0.6, 0.4), (0.88, 0.68), (0.6, 0.98), (0.1, 0.9)]],
          [[(0.2, 0.0), (0.15, 0.45), (0.6, 0.4), (0.88, 0.68), (0.6, 0.98), (0.1, 0.9)], [(0.2, 0.0), (0.85, 0.0)]]],
    "6": [[[(0.75, 0.0), (0.3, 0.3), (0.1, 0.7), (0.35, 1.0), (0.8, 0.85), (0.7, 0.55), (0.15, 0.65)]]],
    "7": [[[(0.05, 0.0), (0.95, 0.0), (0.35, 1.0)]], [[(0.05, 0.0), (0.95, 0.0), (0.35, 1.0)], [(0.3, 0.5), (0.8, 0.5)]]],
    "8": [[_eight()]],
    "9": [[[(0.85, 0.2), (0.5, 0.0), (0.15, 0.2), (0.35, 0.48), (0.85, 0.3), (0.85, 0.6), (0.7, 1.0)]],
          [_ellipse(0.5, 0.25, 0.35, 0.25, 0.0, -1.0) + [(0.85, 0.3), (0.8, 1.0)]]],
}

Cloud = list[tuple[float, float, int]]


def _length(points: Cloud) -> float:
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(points, points[1:]) if a[2] == b[2])


def _resample(points: Cloud, n: int = POINTS) -> Cloud:
    interval = _length(points) / (n - 1)
    if interval <= 0:
        return [points[0]] * n
    out, distance, pts = [points[0]], 0.0, list(points)
    i = 1
    while i < len(pts):
        a, b = pts[i - 1], pts[i]
        if a[2] == b[2]:
            step = math.dist(a[:2], b[:2])
            if distance + step >= interval and step > 0:
                t = (interval - distance) / step
                q = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), b[2])
                out.append(q)
                pts.insert(i, q)
                distance = 0.0
            else:
                distance += step
        i += 1
    while len(out) < n:
        out.append(pts[-1])
    return out[:n]


def _normalize(points: Cloud) -> Cloud:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    scale = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    return [((p[0] - cx) / scale, (p[1] - cy) / scale, p[2]) for p in points]


def cloud(strokes: list[Path]) -> Cloud:
    flat = [(x, y, index) for index, stroke in enumerate(strokes) for x, y in stroke]
    return _normalize(_resample(flat))


def _cloud_distance(a: Cloud, b: Cloud, start: int) -> float:
    n = len(a)
    matched = [False] * n
    total, i = 0.0, start
    for weight_index in range(n):
        best, best_j = math.inf, 0
        for j in range(n):
            if not matched[j]:
                d = math.dist(a[i][:2], b[j][:2])
                if d < best:
                    best, best_j = d, j
        matched[best_j] = True
        total += (1 - weight_index / n) * best
        i = (i + 1) % n
    return total


def _greedy(a: Cloud, b: Cloud) -> float:
    n = len(a)
    step = max(1, int(n ** 0.5))
    return min(min(_cloud_distance(a, b, i), _cloud_distance(b, a, i)) for i in range(0, n, step)) / n


def _aspect(strokes: list[Path]) -> float:
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    return max(max(xs) - min(xs), 0.05) / max(max(ys) - min(ys), 0.05)


def _ordered(a: Cloud, b: Cloud) -> float:
    forward = sum(math.dist(p[:2], q[:2]) for p, q in zip(a, b))
    backward = sum(math.dist(p[:2], q[:2]) for p, q in zip(a, reversed(b)))
    return min(forward, backward) / len(a)


@lru_cache(maxsize=1)
def _templates() -> list[tuple[str, Cloud, float]]:
    return [(digit, cloud(variant), _aspect(variant)) for digit, variants in TEMPLATES.items() for variant in variants]


def recognize(strokes: list[Path]) -> str:
    if not strokes or not any(len(s) > 1 for s in strokes):
        return ""
    if _aspect(strokes) < 0.25:
        return "1"
    candidate, aspect = cloud(strokes), _aspect(strokes)
    digit, score = min(((d, _greedy(candidate, t) + ORDER_WEIGHT * _ordered(candidate, t) + ASPECT_WEIGHT * abs(math.log(aspect / a))) for d, t, a in _templates()),
                       key=lambda r: r[1])
    return digit if score <= MAX_DISTANCE else ""
