import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1] / "biometrics"))
import embeddings as emb

log = logging.getLogger("atena.vision")

FACES = Path(os.environ.get("ATENA_FACES_DIR", "/var/lib/atena/faces"))
MATCH_THRESHOLD = float(os.environ.get("ATENA_FACE_THRESHOLD", "0.40"))
MARGIN = float(os.environ.get("ATENA_FACE_MARGIN", "0.05"))
TWIN_SIM = float(os.environ.get("ATENA_FACE_TWIN_SIM", "0.55"))
TWIN_MARGIN = float(os.environ.get("ATENA_FACE_TWIN_MARGIN", "0.12"))
IR_WEIGHT = float(os.environ.get("ATENA_FACE_IR_WEIGHT", "0.35"))
ADAPTIVE = os.environ.get("ATENA_FACE_ADAPTIVE", "1") != "0"
MAX_SAMPLES = 40
UNKNOWN = "Sconosciuto"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "persona"


def _load_rows(path: Path) -> np.ndarray | None:
    try:
        return emb.unit_rows(np.load(path))
    except (OSError, ValueError):
        return None


class Gallery:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.people: dict = {}
        self.twins: set = set()
        self.reload()

    def reload(self) -> None:
        people = {}
        FACES.mkdir(parents=True, exist_ok=True)
        for d in FACES.iterdir():
            try:
                meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            rows = _load_rows(d / "embeddings.npy")
            if rows is None:
                continue
            ir = _load_rows(d / "embeddings_ir.npy")
            people[d.name] = {**meta, "slug": d.name, "embeddings": rows, "ir": ir}
        self._finish(people)
        log.info("Galleria: %d persone registrate, %d coppie somiglianti", len(people), len(self.twins))

    def _finish(self, people: dict) -> None:
        for p in people.values():
            p["threshold"] = emb.person_threshold(p["embeddings"], MATCH_THRESHOLD) if ADAPTIVE else MATCH_THRESHOLD
            p["threshold_ir"] = emb.person_threshold(p["ir"], MATCH_THRESHOLD) if ADAPTIVE and p["ir"] is not None else MATCH_THRESHOLD
            p["centroid"] = emb.centroid(p["embeddings"])
        twins = emb.twin_pairs({s: p["centroid"] for s, p in people.items()}, TWIN_SIM)
        with self.lock:
            self.people, self.twins = people, twins

    def scores(self, feature: np.ndarray, ir_feature: np.ndarray | None = None) -> tuple[dict, dict | None]:
        with self.lock:
            rgb = {s: emb.score_against(p["embeddings"], feature) for s, p in self.people.items()}
            ir = {s: emb.score_against(p["ir"], ir_feature) for s, p in self.people.items() if p["ir"] is not None} \
                if ir_feature is not None else None
        return rgb, ir or None

    def match_ex(self, feature: np.ndarray, ir_feature: np.ndarray | None = None) -> dict:
        rgb, ir = self.scores(feature, ir_feature)
        fused, conflict = emb.fuse(rgb, ir, IR_WEIGHT, MATCH_THRESHOLD)
        with self.lock:
            limits = {s: p["threshold"] for s, p in self.people.items()}
            twins = set(self.twins)
            names = {s: p["name"] for s, p in self.people.items()}
        result = emb.decide(fused, limits, MATCH_THRESHOLD, MARGIN, TWIN_MARGIN, twins, conflict)
        result["name"] = names.get(result["slug"], UNKNOWN)
        result["names"] = [names[s] for s in (result["best"], result["second"]) if s in names] if result["ambiguous"] else []
        result["twin"] = bool(result["best"] and result["second"]) and frozenset((result["best"], result["second"])) in twins
        return result

    def match(self, feature: np.ndarray, ir_feature: np.ndarray | None = None) -> tuple:
        r = self.match_ex(feature, ir_feature)
        if r["slug"]:
            return r["slug"], r["name"], r["score"]
        return None, UNKNOWN, r["score"]

    def closest(self, feature: np.ndarray) -> tuple[str | None, float]:
        best = (None, 0.0)
        with self.lock:
            for slug, p in self.people.items():
                score = emb.score_against(p["embeddings"], feature)
                if score > best[1]:
                    best = (slug, score)
        return best

    def may_learn(self, slug: str, feature: np.ndarray, ir_feature: np.ndarray | None = None) -> bool:
        r = self.match_ex(feature, ir_feature)
        if r["slug"] != slug:
            return False
        if r["twin"]:
            return r["score"] - r["second_score"] >= TWIN_MARGIN
        return r["score"] >= self.people.get(slug, {}).get("threshold", MATCH_THRESHOLD) + 0.08

    def next_guest_name(self) -> str:
        with self.lock:
            used = {p["name"] for p in self.people.values()}
        n = 1
        while f"Ospite {n}" in used:
            n += 1
        return f"Ospite {n}"

    def add_samples(self, slug: str, rgb: list, ir: list | None = None) -> None:
        d = FACES / slug
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        merged = emb.merge(_load_rows(d / "embeddings.npy"), np.array(rgb), MAX_SAMPLES)
        np.save(d / "embeddings.npy", merged.astype(np.float32))
        meta.update(samples=len(merged), updated=time.time())
        if ir:
            merged_ir = emb.merge(_load_rows(d / "embeddings_ir.npy"), np.array(ir), MAX_SAMPLES)
            np.save(d / "embeddings_ir.npy", merged_ir.astype(np.float32))
            meta["samples_ir"] = len(merged_ir)
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        self.reload()

    def rename(self, slug: str, name: str) -> dict | None:
        d = FACES / slug
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        meta.update(name=name, auto=False, renamed_at=time.time())
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        self.reload()
        return {**meta, "slug": slug}

    def save(self, name: str, embeddings: list, photo: np.ndarray, auto: bool = False, slug: str | None = None,
             ir: list | None = None) -> dict:
        slug = slug or slugify(name)
        d = FACES / slug
        d.mkdir(parents=True, exist_ok=True)
        merged = emb.merge(_load_rows(d / "embeddings.npy"), np.array(embeddings), MAX_SAMPLES)
        np.save(d / "embeddings.npy", merged.astype(np.float32))
        meta = {"name": name, "enrolled_at": time.time(), "samples": len(merged), "auto": auto}
        if ir:
            merged_ir = emb.merge(_load_rows(d / "embeddings_ir.npy"), np.array(ir), MAX_SAMPLES)
            np.save(d / "embeddings_ir.npy", merged_ir.astype(np.float32))
            meta["samples_ir"] = len(merged_ir)
        cv2.imwrite(str(d / "photo.jpg"), photo)
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        os.chmod(d, 0o700)
        self.reload()
        return {**meta, "slug": slug}

    def delete(self, slug: str) -> bool:
        d = FACES / slug
        if not d.is_dir() or d.parent != FACES:
            return False
        shutil.rmtree(d)
        self.reload()
        return True

    def listing(self) -> list:
        with self.lock:
            return [{k: v for k, v in p.items() if k not in ("embeddings", "ir", "centroid")} for p in self.people.values()]

    def health(self) -> list[dict]:
        with self.lock:
            people, twins = dict(self.people), set(self.twins)
        sims = emb.centroid_similarities({s: p["centroid"] for s, p in people.items()})
        rows = []
        for slug, p in people.items():
            stats = emb.intra_stats(p["embeddings"])
            similar = [{"slug": other, "name": people[other]["name"], "similarity": round(sims[frozenset((slug, other))], 3)}
                       for other in people if other != slug and frozenset((slug, other)) in twins]
            samples, ir = len(p["embeddings"]), 0 if p["ir"] is None else len(p["ir"])
            rows.append({"slug": slug, "name": p["name"], "samples": samples, "samples_ir": ir,
                         "threshold": round(p["threshold"], 3), "threshold_ir": round(p["threshold_ir"], 3),
                         "spread": round(stats[1], 3) if stats else None, "similar": similar,
                         "quality": quality(samples, ir, stats, bool(similar))})
        return sorted(rows, key=lambda r: r["name"].lower())


def quality(samples: int, ir: int, stats: tuple | None, has_twin: bool) -> str:
    if samples < 6:
        return "da migliorare"
    if has_twin and (ir < 8 or samples < 20):
        return "da migliorare"
    if samples >= 15 and (stats is None or stats[1] < 0.12):
        return "ottima"
    return "buona"
