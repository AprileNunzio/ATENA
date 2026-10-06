import io
import re
import numpy as np
from PIL import Image, ImageDraw
from features.whiteboard import digits, solver, strokes as ink

MATH_PATTERN = re.compile(r"[\d\s+\-*/x×÷:^().,=]+")

def _classify_glyph(crop: np.ndarray) -> str:
    h, w = crop.shape
    if h < 5 or w < 3:
        return ""
    r_s = np.sum(crop, axis=1)
    c_s = np.sum(crop, axis=0)
    top_band = r_s[:max(2, h // 2)]
    bot_band = r_s[max(2, h // 2):]
    mid_gap = np.min(r_s[max(1, h // 3): max(2, 2 * h // 3)]) if h >= 6 else 999
    if np.max(top_band) >= 6 and np.max(bot_band) >= 6 and mid_gap <= 3 and w >= h * 0.45:
        return "="
    v_peak = np.max(c_s)
    h_peak = np.max(r_s)
    if v_peak >= h * 0.65 and h_peak >= w * 0.65:
        mid_x = np.argmax(c_s)
        mid_y = np.argmax(r_s)
        if 0.15 * w <= mid_x <= 0.85 * w and 0.15 * h <= mid_y <= 0.85 * h:
            return "+"
    if w >= h * 1.75 and np.max(r_s) >= w * 0.7:
        return "-"
    if h >= w * 2.0:
        return "1"
    base_sum = np.max(r_s[-max(3, h // 4):])
    top_sum = np.max(r_s[:max(3, h // 4)])
    if base_sum >= w * 0.5 and top_sum < w * 0.85:
        return "2"
    top_third = crop[:max(2, h // 3), :]
    mid_third = crop[max(2, h // 3): max(3, 2 * h // 3), :]
    bot_third = crop[max(3, 2 * h // 3):, :]
    left_half = crop[:, :max(2, w // 2)]
    right_half = crop[:, max(2, w // 2):]
    if np.sum(right_half) > np.sum(left_half) * 1.5 and np.max(np.sum(mid_third, axis=1)) < np.max(np.sum(top_third, axis=1)):
        return "3"
    center_val = crop[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    if np.mean(center_val) < 0.2 and np.mean(crop) > 0.35 and abs(w - h) < max(w, h) * 0.5:
        return "0"
    if top_sum >= w * 0.6 and np.sum(crop[-max(2, h // 3):, :max(2, w // 2)]) < np.sum(crop[-max(2, h // 3):, max(2, w // 2):]):
        return "7"
    if v_peak >= h * 0.6 and h_peak >= w * 0.5:
        return "4"
    if top_sum >= w * 0.6 and base_sum < w * 0.7:
        return "5"
    if np.sum(bot_third) > np.sum(top_third) * 1.3:
        return "6"
    if np.sum(top_third) > np.sum(bot_third) * 1.3:
        return "9"
    diag1 = np.trace(crop)
    diag2 = np.trace(np.fliplr(crop))
    if diag1 > 0 and diag2 > 0 and abs(w - h) < max(w, h) * 0.4:
        return "x"
    return ""

def _segment_image(arr: np.ndarray):
    row_sums = np.sum(arr, axis=1)
    y_idx = np.where(row_sums > 0)[0]
    if len(y_idx) == 0:
        return []
    
    # Trova le righe (bande orizzontali)
    bands = []
    in_band = False
    start_y = 0
    for i, s in enumerate(row_sums):
        if s > 0 and not in_band:
            in_band = True
            start_y = i
        elif s == 0 and in_band:
            in_band = False
            if i - start_y >= 5:
                bands.append((start_y, i))
    if in_band and len(row_sums) - start_y >= 5:
        bands.append((start_y, len(row_sums)))
        
    if not bands:
        return []
        
    # Prendi l'ultima banda (l'ultima equazione scritta più in basso)
    last_band = bands[-1]
    min_y, max_y = last_band[0], last_band[1]
    
    sub = arr[min_y:max_y, :]
    col_sums = np.sum(sub, axis=0)
    x_idx = np.where(col_sums > 0)[0]
    if len(x_idx) == 0:
        return []
        
    min_x, max_x = x_idx[0], x_idx[-1] + 1
    sub = sub[:, min_x:max_x]
    sub_cols = np.sum(sub, axis=0)
    
    segments = []
    in_seg = False
    start = 0
    for i, s in enumerate(sub_cols):
        if s > 0 and not in_seg:
            in_seg = True
            start = i
        elif s == 0 and in_seg:
            in_seg = False
            if i - start >= 2:
                segments.append((min_x + start, min_x + i))
    if in_seg and len(sub_cols) - start >= 2:
        segments.append((min_x + start, min_x + len(sub_cols)))
        
    chars = []
    for sx0, sx1 in segments:
        col_crop = arr[min_y:max_y, sx0:sx1]
        c_rows = np.sum(col_crop, axis=1)
        cy = np.where(c_rows > 0)[0]
        if len(cy) == 0:
            continue
        g_y0, g_y1 = min_y + cy[0], min_y + cy[-1] + 1
        glyph = arr[g_y0:g_y1, sx0:sx1]
        char = _classify_glyph(glyph)
        chars.append((char, sx0, sx1, g_y0, g_y1))
    return chars

def _render_strokes(strokes: list[dict], width: int = 1600, height: int = 900) -> np.ndarray:
    im = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(im)
    for s in strokes:
        pts = s.get("points") or []
        if len(pts) >= 2:
            draw.line([tuple(p) for p in pts], fill=255, width=max(2, int(s.get("width", 4))))
        elif len(pts) == 1:
            p = pts[0]
            r = max(2, int(s.get("width", 4))) // 2
            draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=255)
    return np.array(im) > 100

def recognize_math(items: list[dict], snapshot_bytes: bytes = b"") -> dict | None:
    if not items:
        return None
    last_item = items[-1]
    
    if last_item.get("by") == "user" and last_item.get("type") == "text":
        raw = last_item.get("text", "").strip()
        clean = raw.rstrip("=").strip()
        if clean and MATH_PATTERN.fullmatch(raw):
            try:
                res = solver.solve(clean)
                return {
                    "expression": raw,
                    "clean": clean,
                    "has_equals": raw.endswith("=") or "=" in raw,
                    "result": res["result"],
                    "speech": res["speech"],
                    "lines": res["lines"],
                    "x": last_item.get("x", 100) + len(raw) * last_item.get("size", 40) * 0.65,
                    "y": last_item.get("y", 100),
                    "size": last_item.get("size", 42),
                    "line": [last_item.get("x", 100), last_item.get("y", 100),
                             last_item.get("x", 100) + len(raw) * last_item.get("size", 40) * 0.52,
                             last_item.get("y", 100) + last_item.get("size", 40) * 1.1],
                }
            except Exception:
                pass
        return None

    user_strokes = [it for it in items if it.get("by") == "user" and it.get("type") == "stroke" and it.get("points")]
    if user_strokes:
        return _from_strokes(user_strokes)
    if not (snapshot_bytes and snapshot_bytes.startswith(b"\xff\xd8")):
        return None
    try:
        im = Image.open(io.BytesIO(snapshot_bytes)).convert("L")
    except Exception:
        return None
    arr = np.array(im) > 95
    scale_x, scale_y = 1600.0 / im.width, 900.0 / im.height
    glyphs = _segment_image(arr)
    if not glyphs:
        return None
    raw_expr = "".join(g[0] for g in glyphs)
    first, last = glyphs[0], glyphs[-1]
    line = (first[1] * scale_x, min(g[3] for g in glyphs) * scale_y, last[2] * scale_x, max(g[4] for g in glyphs) * scale_y)
    return _result(raw_expr, line)


def _digit(glyph: "ink.Glyph") -> str:
    return digits.recognize([[(p[0], p[1]) for p in s.points] for s in glyph.strokes])


def _from_strokes(items: list[dict]) -> dict | None:
    parsed = [ink.Stroke([[float(p[0]), float(p[1])] for p in it["points"]]) for it in items]
    newest = parsed[-1]
    row = next((r for r in ink.lines(parsed) if newest in r), None)
    if not row:
        return None
    line_height = max(s.y1 for s in row) - min(s.y0 for s in row)
    chars = [ink.operator(g, line_height) or _digit(g) for g in ink.glyphs(row)]
    line = (min(s.x0 for s in row), min(s.y0 for s in row), max(s.x1 for s in row), max(s.y1 for s in row))
    return _result("".join(chars), line)


def _result(raw_expr: str, line: tuple) -> dict | None:
    if not raw_expr or not any(c.isdigit() for c in raw_expr):
        return None
    clean_expr = raw_expr.rstrip("=").strip()
    if not clean_expr:
        return None
    try:
        sol = solver.solve(clean_expr.split("=")[0] if clean_expr.count("=") == 1 and "x" not in clean_expr else clean_expr)
    except Exception:
        return None
    x0, y0, x1, y1 = line
    size = min(90.0, max(30.0, (y1 - y0) * 0.9))
    return {
        "expression": raw_expr,
        "clean": clean_expr,
        "has_equals": "=" in raw_expr,
        "result": sol["result"],
        "speech": sol["speech"],
        "lines": sol["lines"],
        "x": min(1500.0, max(50.0, x1 + 24.0)),
        "y": min(850.0, max(10.0, (y0 + y1) / 2 - size * 0.55)),
        "size": size,
        "line": [x0, y0, x1, y1],
    }
