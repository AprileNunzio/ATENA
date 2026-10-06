import json
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1] / "biometrics"))
import embeddings as emb
import earconf

log = logging.getLogger("atena.ear")

MODEL = Path(os.environ.get("ATENA_VOICEPRINT_MODEL", "/opt/atena-ear/voiceprint/speaker.onnx"))
STORE = Path(os.environ.get("ATENA_VOICEPRINTS", "/var/lib/atena/voiceprints"))
RATE = 16000
MIN_SECONDS = 1.0
MAX_SAMPLES = 40
ENROLLED_AT = 5
TOP_K = 3
CENTROID_SHARE = 0.5
LEARN_SLACK = 0.1
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def match_base() -> float:
    return earconf.number("ATENA_VOICEPRINT_MATCH", 0.62, 0.3, 0.95)


def margin() -> float:
    return earconf.number("ATENA_VOICE_MARGIN", 0.06, 0.0, 0.5)


def twin_margin() -> float:
    return earconf.number("ATENA_VOICE_TWIN_MARGIN", 0.12, 0.0, 0.6)


def twin_similarity() -> float:
    return earconf.number("ATENA_VOICE_TWIN_SIM", 0.5, 0.2, 0.95)


def person_score(samples: np.ndarray, centre: np.ndarray, probe: np.ndarray) -> float:
    sims = np.sort(samples @ probe)[::-1]
    return float(CENTROID_SHARE * (centre @ probe) + (1 - CENTROID_SHARE) * sims[:TOP_K].mean())


class Voiceprints:

    def __init__(self) -> None:
        self.extractor = None
        self.lock = threading.Lock()
        self.samples: dict[str, np.ndarray] = {}
        self.centres: dict[str, np.ndarray] = {}
        self.limits: dict[str, float] = {}
        self.twins: set = set()
        self.stamp = 0.0
        if os.environ.get("ATENA_VOICEPRINT", "1") == "0" or not MODEL.exists():
            log.info("Impronta vocale non disponibile su questo sistema")
            return
        try:
            import sherpa_onnx
            config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(MODEL), num_threads=2)
            self.extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
            STORE.mkdir(parents=True, exist_ok=True)
            os.chmod(STORE, 0o700)
            self._load()
            log.info("Impronta vocale attiva: %d persone, %d coppie di voci simili", len(self.samples), len(self.twins))
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            log.warning("Impronta vocale non avviata: %s", exc)
            self.extractor = None

    @property
    def ready(self) -> bool:
        return self.extractor is not None

    def _load(self) -> None:
        samples, centres, limits = {}, {}, {}
        adaptive = earconf.flag("ATENA_VOICE_ADAPTIVE", True)
        for f in STORE.glob("*.npy"):
            try:
                rows = emb.unit_rows(np.load(f))
            except (OSError, ValueError):
                continue
            samples[f.stem], centres[f.stem] = rows, emb.centroid(rows)
            limits[f.stem] = emb.person_threshold(rows, match_base()) if adaptive else match_base()
        twins = emb.twin_pairs(centres, twin_similarity())
        with self.lock:
            self.samples, self.centres, self.limits, self.twins = samples, centres, limits, twins
        self._write_report()

    def _write_report(self) -> None:
        sims = emb.centroid_similarities(self.centres)
        people = {}
        for slug, rows in self.samples.items():
            stats = emb.intra_stats(rows)
            similar = [{"slug": other, "similarity": round(sims[frozenset((slug, other))], 3)}
                       for other in self.samples if other != slug and frozenset((slug, other)) in self.twins]
            people[slug] = {"samples": len(rows), "threshold": round(self.limits[slug], 3),
                            "spread": round(stats[1], 3) if stats else None, "similar": similar,
                            "enrolled": len(rows) >= ENROLLED_AT}
        try:
            tmp = STORE / "report.tmp"
            tmp.write_text(json.dumps({"updated": time.time(), "twin_similarity": twin_similarity(), "people": people}), encoding="utf-8")
            os.replace(tmp, STORE / "report.json")
        except OSError as exc:
            log.debug("Resoconto delle voci non salvato: %s", exc)

    def embed(self, audio: np.ndarray) -> np.ndarray | None:
        if not self.ready or len(audio) < RATE * MIN_SECONDS:
            return None
        stream = self.extractor.create_stream()
        stream.accept_waveform(RATE, audio.astype(np.float32))
        stream.input_finished()
        if not self.extractor.is_ready(stream):
            return None
        return emb.unit(np.array(self.extractor.compute(stream), dtype=np.float32))

    def _refresh(self) -> None:
        try:
            stamp = STORE.stat().st_mtime
        except OSError:
            return
        if stamp != self.stamp:
            self.stamp = stamp
            self._load()

    def scores(self, probe: np.ndarray) -> dict:
        with self.lock:
            return {slug: person_score(rows, self.centres[slug], probe) for slug, rows in self.samples.items()}

    def verdict(self, probe: np.ndarray) -> dict:
        with self.lock:
            limits, twins = dict(self.limits), set(self.twins)
        return emb.decide(self.scores(probe), limits, match_base(), margin(), twin_margin(), twins)

    def identify(self, probe: np.ndarray | None) -> tuple[str | None, float]:
        if probe is None:
            return None, 0.0
        self._refresh()
        result = self.verdict(probe)
        return result["slug"], result["score"]

    def may_learn(self, slug: str, probe: np.ndarray, source: str) -> bool:
        if source != "ascolto":
            return True
        if not earconf.flag("ATENA_VOICE_AUTOIMPROVE", True):
            return self.count(slug) < ENROLLED_AT
        if self.count(slug) < ENROLLED_AT:
            return True
        result = self.verdict(probe)
        if result["ambiguous"]:
            return False
        own = self.scores(probe).get(slug, 0.0)
        return own >= self.limits.get(slug, match_base()) - LEARN_SLACK and result["best"] in (slug, None)

    def add(self, slug: str, probe: np.ndarray, source: str) -> int:
        if not _SLUG.match(slug) or probe is None:
            return 0
        path = STORE / f"{slug}.npy"
        try:
            old = np.load(path) if path.exists() else None
        except (OSError, ValueError):
            old = None
        if not self.may_learn(slug, probe, source):
            return 0 if old is None else len(old)
        merged = emb.merge(old, probe, MAX_SAMPLES)
        np.save(path, merged.astype(np.float32))
        meta = {"samples": len(merged), "updated": time.time(), "source": source, "enrolled": len(merged) >= ENROLLED_AT}
        (STORE / f"{slug}.json").write_text(json.dumps(meta), encoding="utf-8")
        self._load()
        return len(merged)

    def count(self, slug: str) -> int:
        try:
            return json.loads((STORE / f"{slug}.json").read_text(encoding="utf-8")).get("samples", 0)
        except (OSError, ValueError):
            return 0

    def forget(self, slug: str) -> None:
        if not _SLUG.match(slug):
            return
        for ext in ("npy", "json"):
            (STORE / f"{slug}.{ext}").unlink(missing_ok=True)
        self._load()
