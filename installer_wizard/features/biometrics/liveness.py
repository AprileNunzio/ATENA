import numpy as np

DARK = 20.0
BRIGHT_OK = 60.0
SATURATED = 245.0
STD_LOW, STD_OK = 8.0, 22.0
CENTER_LOW, CENTER_HIGH = 1.02, 2.4
SUPPORT_LOW, SUPPORT_SPAN = 0.2, 0.4
WEIGHTS = {"presence": 0.40, "agreement": 0.15, "stats": 0.25, "support": 0.20}


def ramp(value: float, low: float, high: float) -> float:
    if high <= low:
        return 1.0
    return float(min(1.0, max(0.0, (value - low) / (high - low))))


def crop(gray: np.ndarray, box, pad: float = 0.08) -> np.ndarray | None:
    h, w = gray.shape[:2]
    x, y, bw, bh = (float(v) for v in box)
    x0, y0 = max(0, int(x - bw * pad)), max(0, int(y - bh * pad))
    x1, y1 = min(w, int(x + bw * (1 + pad))), min(h, int(y + bh * (1 + pad)))
    if x1 - x0 < 12 or y1 - y0 < 12:
        return None
    return gray[y0:y1, x0:x1]


def metrics(gray: np.ndarray, box) -> dict | None:
    roi = crop(gray, box)
    if roi is None:
        return None
    roi = roi.astype(np.float32)
    h, w = roi.shape
    inner = roi[h // 4:h - h // 4, w // 4:w - w // 4]
    ring_sum = roi.sum() - inner.sum()
    ring_n = roi.size - inner.size
    ring = ring_sum / max(1, ring_n)
    gy, gx = np.gradient(roi)
    return {"mean": float(roi.mean()), "std": float(roi.std()), "saturated": float((roi >= SATURATED).mean()),
            "texture": float(np.mean(np.abs(gx)) + np.mean(np.abs(gy))),
            "center_ratio": float(inner.mean() / max(ring, 1.0))}


def stats_score(m: dict) -> float:
    brightness = ramp(m["mean"], DARK, BRIGHT_OK) * (1.0 - min(1.0, m["saturated"] * 4))
    texture = ramp(m["std"], STD_LOW, STD_OK)
    center = ramp(m["center_ratio"], CENTER_LOW - 0.04, CENTER_LOW + 0.1) * (1.0 - ramp(m["center_ratio"], CENTER_HIGH, CENTER_HIGH + 0.8))
    return float(0.4 * brightness + 0.4 * texture + 0.2 * center)


def box_agreement(rgb_box, rgb_size, ir_box, ir_size, offset: tuple = (0.0, 0.0)) -> float:
    rx = (rgb_box[0] + rgb_box[2] / 2) / rgb_size[0] + offset[0]
    ry = (rgb_box[1] + rgb_box[3] / 2) / rgb_size[1] + offset[1]
    ix = (ir_box[0] + ir_box[2] / 2) / ir_size[0]
    iy = (ir_box[1] + ir_box[3] / 2) / ir_size[1]
    dist = float(np.hypot(rx - ix, ry - iy))
    rs = rgb_box[2] / rgb_size[0]
    ss = ir_box[2] / ir_size[0]
    ratio = min(rs, ss) / max(rs, ss, 1e-6)
    return float(ramp(0.35 - dist, 0.0, 0.25) * ramp(ratio, 0.35, 0.8))


def assess(has_sensor: bool, ir_found: bool, ir_metrics: dict | None, agreement: float, support: float | None,
           minimum: float) -> dict:
    if not has_sensor:
        return {"state": "unknown", "score": None, "parts": {}}
    parts = {"presence": 1.0 if ir_found else 0.0}
    if ir_found:
        parts["agreement"] = agreement
        if ir_metrics:
            parts["stats"] = stats_score(ir_metrics)
        if support is not None:
            parts["support"] = ramp(support - SUPPORT_LOW, 0.0, SUPPORT_SPAN)
    total = sum(WEIGHTS[k] for k in parts)
    score = sum(WEIGHTS[k] * v for k, v in parts.items()) / total
    return {"state": "live" if score >= minimum else "spoof", "score": round(float(score), 3),
            "parts": {k: round(float(v), 3) for k, v in parts.items()}}


def smooth(previous: float | None, new: float, alpha: float = 0.35) -> float:
    return new if previous is None else previous + (new - previous) * alpha
