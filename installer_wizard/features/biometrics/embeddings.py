import numpy as np

THRESHOLD_FLOOR_DELTA = 0.08
THRESHOLD_CEIL_DELTA = 0.12
MIN_FOR_STATS = 6
SIGMA_FACTOR = 2.5


def unit(v: np.ndarray) -> np.ndarray:
    return v / max(float(np.linalg.norm(v)), 1e-9)


def unit_rows(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    if m.ndim == 1:
        m = m[None, :]
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)


def centroid(emb: np.ndarray) -> np.ndarray:
    return unit(unit_rows(emb).mean(axis=0))


def redundancy(emb: np.ndarray) -> np.ndarray:
    rows = unit_rows(emb)
    if len(rows) < 2:
        return np.zeros(len(rows), dtype=np.float32)
    sims = rows @ rows.T
    np.fill_diagonal(sims, -1.0)
    return sims.max(axis=1)


def prune(emb: np.ndarray, limit: int) -> np.ndarray:
    rows = unit_rows(emb)
    while len(rows) > limit:
        scores = redundancy(rows)
        newest_protected = len(rows) - 1
        scores[newest_protected] = -2.0
        rows = np.delete(rows, int(np.argmax(scores)), axis=0)
    return rows


def merge(old: np.ndarray | None, new: np.ndarray, limit: int) -> np.ndarray:
    fresh = unit_rows(new)
    if old is None or len(old) == 0:
        return prune(fresh, limit)
    return prune(np.vstack([unit_rows(old), fresh]), limit)


def intra_stats(emb: np.ndarray) -> tuple[float, float] | None:
    rows = unit_rows(emb)
    if len(rows) < MIN_FOR_STATS:
        return None
    best = redundancy(rows)
    return float(best.mean()), float(best.std())


def person_threshold(emb: np.ndarray, base: float) -> float:
    stats = intra_stats(emb)
    if stats is None:
        return base
    mu, sigma = stats
    return float(min(base + THRESHOLD_CEIL_DELTA, max(base - THRESHOLD_FLOOR_DELTA, mu - SIGMA_FACTOR * sigma)))


def score_against(emb: np.ndarray, probe: np.ndarray) -> float:
    return float(np.max(unit_rows(emb) @ unit(probe)))


def centroid_similarities(centroids: dict) -> dict:
    keys = sorted(centroids)
    out = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            out[frozenset((a, b))] = float(centroids[a] @ centroids[b])
    return out


def twin_pairs(centroids: dict, limit: float) -> set:
    return {pair for pair, sim in centroid_similarities(centroids).items() if sim >= limit}


def fuse(primary: dict, secondary: dict | None, weight: float, floor: float = 0.0) -> tuple[dict, bool]:
    if not secondary:
        return dict(primary), False
    fused = {}
    for slug in set(primary) | set(secondary):
        if slug in primary and slug in secondary:
            fused[slug] = (1 - weight) * primary[slug] + weight * secondary[slug]
        else:
            fused[slug] = primary.get(slug, secondary.get(slug))
    top_a = max(primary, key=primary.get) if primary else None
    top_b = max(secondary, key=secondary.get) if secondary else None
    return fused, bool(top_a and top_b and top_a != top_b and secondary[top_b] >= floor)


def decide(scores: dict, thresholds: dict, base: float, margin: float, twin_margin: float, twins: set,
           conflict: bool = False) -> dict:
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked:
        return {"slug": None, "best": None, "score": 0.0, "second": None, "second_score": 0.0, "ambiguous": False,
                "reason": "nessuno"}
    (slug, best), (second, second_score) = ranked[0], ranked[1] if len(ranked) > 1 else (None, 0.0)
    out = {"slug": None, "best": slug, "score": best, "second": second, "second_score": second_score, "ambiguous": False,
           "reason": ""}
    if best < thresholds.get(slug, base):
        out["reason"] = "sotto soglia"
        return out
    needed = twin_margin if second is not None and frozenset((slug, second)) in twins else margin
    if second is not None and second_score >= base * 0.8 and best - second_score < needed:
        out.update(ambiguous=True, reason="troppo simile a un'altra persona")
        return out
    if conflict:
        out.update(ambiguous=True, reason="volto visibile e infrarosso non concordano")
        return out
    out.update(slug=slug, reason="ok")
    return out
