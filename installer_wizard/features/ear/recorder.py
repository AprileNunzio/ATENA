import json
import logging
import os
import time
import uuid
import wave
from collections import deque
from pathlib import Path

import numpy as np

import earconf

log = logging.getLogger("atena.ear")

RATE = 16000
FRAME = 480
FRAME_S = FRAME / RATE
PRE_FRAMES = 14
TAIL_FRAMES = 20
MIN_VOICED = 1.5
OVERRUN = 25.0
CLIP_LEVEL = 0.98
ROOT = Path(os.environ.get("ATENA_EAR_REVIEW_DIR", "/var/lib/atena/ear_review"))
RECORDS = ROOT / "chunks"


def enabled() -> bool:
    return earconf.flag("ATENA_EAR_RECORD", True)


def chunk_seconds() -> float:
    return earconf.number("ATENA_EAR_RECORD_CHUNK", 60.0, 20.0, 300.0)


class Chunk:

    def __init__(self, meta: dict, audio: np.ndarray) -> None:
        self.meta = meta
        self.audio = audio


class Recorder:

    def __init__(self, source: str) -> None:
        self.source = source
        self.preroll: deque = deque(maxlen=PRE_FRAMES)
        self.hold_until = 0.0
        self.begin(time.time())

    def begin(self, now: float) -> None:
        self.start = now
        self.wall = now
        self.layout: list = []
        self.parts: list = []
        self.open: dict | None = None
        self.tail = 0
        self.wav_len = 0
        self.voiced_rms: list = []
        self.noise_sum = 0.0
        self.noise_n = 0
        self.clipped = 0
        self.events: list = []

    def hold(self, seconds: float) -> None:
        self.hold_until = max(self.hold_until, time.time() + seconds)

    def note(self, kind: str, **data) -> None:
        if enabled():
            self.events.append({"kind": kind, "t": round(time.time() - self.start, 2), **data})

    def _close(self) -> None:
        seg, self.open = self.open, None
        if not seg:
            return
        audio = np.concatenate(seg["frames"])
        self.layout.append([round(seg["t_off"], 3), round(self.wav_len / RATE, 3), round(len(audio) / RATE, 3)])
        self.parts.append(audio)
        self.wav_len += len(audio)

    def feed(self, frame: np.ndarray, rms: float, voiced: bool, noise: float, now: float, blocked: bool,
             profile: np.ndarray | None) -> Chunk | None:
        if not enabled():
            self.preroll.clear()
            return None
        if blocked:
            self._close()
            self.preroll.clear()
        elif voiced:
            if self.open is None:
                lead = len(self.preroll) * FRAME_S
                self.open = {"t_off": max(0.0, now - self.start - lead), "frames": list(self.preroll)}
                self.preroll.clear()
            self.open["frames"].append(frame)
            self.tail = TAIL_FRAMES
            self.voiced_rms.append(rms)
            if float(np.max(np.abs(frame))) >= CLIP_LEVEL:
                self.clipped += 1
        elif self.open is not None:
            self.open["frames"].append(frame)
            self.tail -= 1
            if self.tail <= 0:
                self._close()
        else:
            self.preroll.append(frame)
            self.noise_sum += noise
            self.noise_n += 1
        elapsed = now - self.start
        if elapsed < chunk_seconds() or (self.open is not None and elapsed < chunk_seconds() + OVERRUN):
            return None
        if now < self.hold_until and elapsed < chunk_seconds() + OVERRUN:
            return None
        return self._finish(now, profile)

    def _finish(self, now: float, profile: np.ndarray | None) -> Chunk | None:
        self._close()
        voiced_s = len(self.voiced_rms) * FRAME_S
        chunk = None
        if self.parts and voiced_s >= MIN_VOICED:
            rms = sorted(self.voiced_rms)
            meta = {"id": uuid.uuid4().hex[:12], "source": self.source, "started": self.wall, "duration": round(now - self.start, 2),
                    "voiced_s": round(voiced_s, 2), "layout": self.layout, "events": self.events,
                    "speech_p50": round(rms[len(rms) // 2], 5), "speech_p90": round(rms[int(len(rms) * 0.9)], 5),
                    "noise": round(self.noise_sum / self.noise_n, 5) if self.noise_n else 0.0,
                    "clip_frac": round(self.clipped / max(1, len(rms)), 4), "reviewed": False,
                    "noise_profile": [round(float(x), 5) for x in profile] if profile is not None else None}
            chunk = Chunk(meta, np.concatenate(self.parts))
        self.begin(now)
        return chunk


def write_chunk(chunk: Chunk) -> None:
    RECORDS.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(ROOT, 0o700)
        os.chmod(RECORDS, 0o700)
    except OSError as exc:
        log.debug("Permessi della cartella delle registrazioni: %s", exc)
    base = RECORDS / f"c{int(chunk.meta['started'])}_{chunk.meta['id']}"
    pcm = (np.clip(chunk.audio, -1, 1) * 32767).astype("<i2").tobytes()
    tmp = base.with_suffix(".wav.tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    os.replace(tmp, base.with_suffix(".wav"))
    meta_tmp = base.with_suffix(".json.tmp")
    meta_tmp.write_text(json.dumps(chunk.meta, ensure_ascii=False), encoding="utf-8")
    os.replace(meta_tmp, base.with_suffix(".json"))
    os.chmod(base.with_suffix(".wav"), 0o600)
    os.chmod(base.with_suffix(".json"), 0o600)
    prune()


def listing() -> list[tuple[Path, dict]]:
    rows = []
    for meta_file in sorted(RECORDS.glob("c*.json")):
        try:
            rows.append((meta_file, json.loads(meta_file.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as exc:
            log.warning("Registrazione %s illeggibile: %s", meta_file.name, exc)
    return rows


def remove(meta_file: Path) -> None:
    for suffix in (".wav", ".json"):
        try:
            meta_file.with_suffix(suffix).unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            log.warning("Registrazione non eliminata (%s): %s", meta_file.name, exc)


def prune() -> int:
    now = time.time()
    keep = earconf.number("ATENA_EAR_RECORD_HOURS", 24.0, 1.0, 168.0) * 3600
    keep_done = earconf.number("ATENA_EAR_KEEP_REVIEWED_H", 2.0, 0.0, 48.0) * 3600
    cap = earconf.number("ATENA_EAR_RECORD_MAX_MB", 500.0, 50.0, 5000.0) * 1024 * 1024
    rows = listing()
    removed = 0
    alive = []
    for meta_file, meta in rows:
        age = now - float(meta.get("started", now))
        reviewed_at = float(meta.get("reviewed_at") or 0)
        if age > keep or (reviewed_at and now - reviewed_at > keep_done):
            remove(meta_file)
            removed += 1
        else:
            alive.append((meta_file, meta))
    total = sum(f.with_suffix(".wav").stat().st_size for f, _ in alive if f.with_suffix(".wav").exists())
    for meta_file, _ in alive:
        if total <= cap:
            break
        size = meta_file.with_suffix(".wav").stat().st_size if meta_file.with_suffix(".wav").exists() else 0
        remove(meta_file)
        total -= size
        removed += 1
    return removed


def purge() -> int:
    count = 0
    for meta_file, _ in listing():
        remove(meta_file)
        count += 1
    for stray in RECORDS.glob("*.tmp"):
        stray.unlink(missing_ok=True)
    return count
