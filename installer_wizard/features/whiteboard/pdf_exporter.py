import base64
import io
import math
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1600, 900
BG_COLOR = (18, 33, 27)

def _hex_to_rgb(hex_code: str, fallback: tuple[int, int, int] = (244, 244, 240)) -> tuple[int, int, int]:
    raw = str(hex_code or "").lstrip("#")
    if len(raw) == 6:
        try:
            return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
        except ValueError:
            pass
    return fallback

def _get_font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()

def render_page_image(page: dict, page_num: int, total_pages: int) -> Image.Image:
    snapshot = page.get("snapshot")
    if snapshot and isinstance(snapshot, (bytes, bytearray)) and snapshot.startswith(b"\xff\xd8"):
        try:
            base = Image.open(io.BytesIO(snapshot)).convert("RGB")
            if base.size != (WIDTH, HEIGHT):
                base = base.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            return base
        except Exception:
            pass
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    items = page.get("items", [])
    for it in items:
        t = it.get("type")
        c = _hex_to_rgb(it.get("color", "#f4f4f0"))
        w = max(1, int(float(it.get("width", 4))))
        if t in ("stroke", "erase"):
            pts = [tuple(p) for p in it.get("points", []) if isinstance(p, (list, tuple)) and len(p) == 2]
            if len(pts) >= 2:
                stroke_c = BG_COLOR if t == "erase" else c
                draw.line(pts, fill=stroke_c, width=w * 3 if t == "erase" else w, joint="curve")
            elif len(pts) == 1:
                stroke_c = BG_COLOR if t == "erase" else c
                r = w // 2
                draw.ellipse((pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r), fill=stroke_c)
        elif t == "text":
            font = _get_font(max(14, int(float(it.get("size", 36)))))
            draw.text((float(it.get("x", 50)), float(it.get("y", 50))), str(it.get("text", "")), fill=c, font=font)
        elif t in ("line", "arrow"):
            x1, y1 = float(it.get("x1", 0)), float(it.get("y1", 0))
            x2, y2 = float(it.get("x2", 0)), float(it.get("y2", 0))
            draw.line([(x1, y1), (x2, y2)], fill=c, width=w)
            if t == "arrow":
                ang = math.atan2(y2 - y1, x2 - x1)
                sz = 14 + w * 2
                a1 = (x2 - sz * math.cos(ang - 0.45), y2 - sz * math.sin(ang - 0.45))
                a2 = (x2 - sz * math.cos(ang + 0.45), y2 - sz * math.sin(ang + 0.45))
                draw.line([(x2, y2), a1], fill=c, width=w)
                draw.line([(x2, y2), a2], fill=c, width=w)
        elif t == "rect":
            x1, y1 = float(it.get("x1", 0)), float(it.get("y1", 0))
            x2, y2 = float(it.get("x2", 0)), float(it.get("y2", 0))
            box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            draw.rectangle(box, outline=c, width=w)
        elif t == "ellipse":
            x1, y1 = float(it.get("x1", 0)), float(it.get("y1", 0))
            x2, y2 = float(it.get("x2", 0)), float(it.get("y2", 0))
            box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            draw.ellipse(box, outline=c, width=w)
        elif t in ("formula", "callout", "table", "plot", "chart", "image", "mark"):
            _rich(img, draw, it, c)
    hdr_font = _get_font(18)
    draw.text((30, 20), "ATENA - Lavagna Interattiva", fill=(41, 224, 255), font=hdr_font)
    draw.text((WIDTH - 180, 20), f"Pagina {page_num} di {total_pages}", fill=(180, 190, 195), font=hdr_font)
    return img

def _rich(img: Image.Image, draw: ImageDraw.ImageDraw, it: dict, c: tuple[int, int, int]) -> None:
    t = it.get("type")
    x, y = float(it.get("x", it.get("x1", 0))), float(it.get("y", it.get("y1", 0)))
    if t == "formula":
        font = _get_font(int(it.get("size", 34)))
        for i, line in enumerate(it.get("lines", [])):
            draw.text((x, y + i * it.get("size", 34) * 1.25), str(line), fill=c, font=font)
    elif t == "callout":
        draw.rounded_rectangle((x, y, x + it.get("w", 600), y + it.get("h", 120)), radius=14, outline=(41, 224, 255), width=3, fill=(6, 20, 26))
        draw.text((x + 20, y + 12), str(it.get("title", "")), fill=(255, 209, 102), font=_get_font(26))
        for i, line in enumerate(it.get("lines", [])):
            draw.text((x + 20, y + 54 + i * it.get("size", 30) * 1.35), str(line), fill=(238, 249, 255), font=_get_font(int(it.get("size", 30))))
    elif t == "table":
        size = int(it.get("size", 26))
        rows = ([it["header"]] if it.get("header") else []) + it.get("rows", [])
        cols = max([len(r) for r in rows] + [1])
        cell = it.get("w", 700) / cols
        if it.get("title"):
            draw.text((x, y), str(it["title"]), fill=(255, 209, 102), font=_get_font(size + 4))
            y += size * 1.4
        for r, row in enumerate(rows):
            for col, value in enumerate(row):
                draw.text((x + col * cell + 8, y + r * size * 1.6), str(value), fill=(41, 224, 255) if r == 0 and it.get("header") else (244, 244, 240), font=_get_font(size))
    elif t == "plot":
        w, h = it.get("w", 700), it.get("h", 400)
        draw.rectangle((x, y, x + w, y + h), outline=(90, 110, 100), width=1)
        sx = lambda v: x + (v - it["xmin"]) / (it["xmax"] - it["xmin"]) * w
        sy = lambda v: y + h - (v - it["ymin"]) / (it["ymax"] - it["ymin"]) * h
        for series in it.get("series", []):
            segment = []
            for px, py in series.get("points", []):
                if py is None or not it["ymin"] <= py <= it["ymax"]:
                    if len(segment) > 1:
                        draw.line(segment, fill=_hex_to_rgb(series.get("color")), width=3)
                    segment = []
                else:
                    segment.append((sx(px), sy(py)))
            if len(segment) > 1:
                draw.line(segment, fill=_hex_to_rgb(series.get("color")), width=3)
    elif t == "chart":
        values = it.get("values", [])
        peak = max([abs(v) for v in values] + [1e-9])
        slot = it.get("w", 700) / max(1, len(values))
        base = y + it.get("h", 380) - 30
        for i, value in enumerate(values):
            top = base - max(value, 0) / peak * (it.get("h", 380) - 70)
            draw.rectangle((x + i * slot + slot * 0.18, top, x + (i + 1) * slot - slot * 0.18, base), fill=(41, 224, 255))
            draw.text((x + i * slot + 6, base + 6), str(it.get("labels", [""] * len(values))[i]), fill=(244, 244, 240), font=_get_font(16))
    elif t == "image":
        try:
            raw = base64.b64decode(str(it.get("src", "")).split(",", 1)[1])
            picture = Image.open(io.BytesIO(raw)).convert("RGB")
            picture.thumbnail((int(it.get("w", 400)), int(it.get("h", 300))))
            img.paste(picture, (int(x), int(y)))
        except Exception:
            draw.rectangle((x, y, x + it.get("w", 400), y + it.get("h", 300)), outline=(90, 110, 100))
        if it.get("caption"):
            draw.text((x, y + it.get("h", 300) + 8), str(it["caption"]), fill=(200, 205, 200), font=_get_font(18))
    elif t == "mark":
        box = (min(it["x1"], it["x2"]), min(it["y1"], it["y2"]), max(it["x1"], it["x2"]), max(it["y1"], it["y2"]))
        if it.get("style") in ("underline", "wavy"):
            draw.line([(box[0], box[3] + 4), (box[2], box[3] + 4)], fill=c, width=4)
        elif it.get("style") == "strike":
            draw.line([(box[0], (box[1] + box[3]) / 2), (box[2], (box[1] + box[3]) / 2)], fill=c, width=4)
        elif it.get("style") == "circle":
            draw.ellipse((box[0] - 18, box[1] - 14, box[2] + 18, box[3] + 14), outline=c, width=4)
        else:
            draw.rectangle((box[0] - 6, box[1] - 2, box[2] + 6, box[3] + 2), outline=c, width=3)


def export_pages_to_pdf(pages: list[dict]) -> bytes:
    if not pages:
        pages = [{"items": []}]
    total = len(pages)
    rendered = [render_page_image(p, idx + 1, total) for idx, p in enumerate(pages)]
    buf = io.BytesIO()
    rendered[0].save(buf, format="PDF", save_all=True, append_images=rendered[1:], resolution=150.0)
    return buf.getvalue()
