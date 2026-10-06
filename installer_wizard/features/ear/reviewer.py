import asyncio
import json
import logging
import os
import time
import wave
from pathlib import Path

import numpy as np

import earconf
import enhance
import recorder
import review_metrics as metrics
import stt
from learner import TOKEN_RE, learner
from tuning import tuning

log = logging.getLogger("atena.ear")

RATE = 16000
POLL = 30.0
SLICE = 10.0
KEEP_REVIEWS = 400
SUMMARY_WINDOW = 100
REVIEWS = recorder.ROOT / "reviews.jsonl"
SUMMARY = recorder.ROOT / "summary.json"


class Activity:

    def __init__(self) -> None:
        self.last_voice = time.time()

    def voice(self) -> None:
        self.last_voice = time.time()


activity = Activity()


def has_wake(text: str) -> bool:
    return learner.find_wake(text) is not None


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def recent_reviews(limit: int) -> list[dict]:
    try:
        lines = REVIEWS.read_text(encoding="utf-8").splitlines()[-limit:]
    except FileNotFoundError:
        return []
    except OSError as exc:
        log.warning("Storico delle revisioni non letto: %s", exc)
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


class Reviewer:

    def __init__(self, busy) -> None:
        self.busy = busy
        self.state = "in attesa"
        self.current = ""

    def enabled(self) -> bool:
        return recorder.enabled() and earconf.flag("ATENA_EAR_REVIEW", True)

    def resting(self) -> bool:
        idle = earconf.number("ATENA_EAR_REVIEW_IDLE", 120.0, 10.0, 3600.0)
        if time.time() - activity.last_voice < idle or self.busy() or stt.lock.locked():
            return False
        limit = earconf.number("ATENA_EAR_REVIEW_LOAD", 0.6, 0.1, 2.0)
        try:
            load = os.getloadavg()[0] / (os.cpu_count() or 1)
        except (OSError, AttributeError):
            return True
        return load <= limit

    def quiet(self) -> bool:
        idle = earconf.number("ATENA_EAR_REVIEW_IDLE", 120.0, 10.0, 3600.0)
        return time.time() - activity.last_voice >= min(idle, 20.0) and not self.busy()

    async def run(self) -> None:
        self.publish()
        shown = self.state
        while True:
            await asyncio.sleep(POLL)
            if self.state != shown:
                shown = self.state
                await asyncio.to_thread(self.publish)
            try:
                tuning.load()
                if not self.enabled():
                    self.state = "disattivata"
                    continue
                if not self.resting():
                    self.state = "in attesa del riposo"
                    continue
                pending = [(f, m) for f, m in recorder.listing() if not m.get("reviewed")]
                if not pending:
                    self.state = "nulla da rivedere"
                    continue
                await self.review(*pending[0])
            except Exception:
                log.exception("Revisione delle registrazioni interrotta da un errore")
                self.state = "errore"

    def pieces(self, meta: dict, audio: np.ndarray) -> list[tuple[np.ndarray, float]]:
        out = []
        for t_off, wav_off, dur in meta.get("layout") or [[0.0, 0.0, len(audio) / RATE]]:
            begin = int(wav_off * RATE)
            end = min(len(audio), int((wav_off + dur) * RATE))
            step = int(SLICE * RATE)
            for at in range(begin, end, step):
                piece = audio[at:min(end, at + step)]
                if len(piece) > RATE * 0.4:
                    out.append((piece, t_off + (at - begin) / RATE))
        return out

    async def transcribe(self, meta: dict, clean: np.ndarray) -> list[dict] | None:
        name = earconf.text("ATENA_EAR_REVIEW_MODEL", "same", ("same", "base", "small", "medium"))
        segments: list = []
        for piece, t0 in self.pieces(meta, clean):
            if not self.quiet():
                return None
            async with stt.lock:
                try:
                    segments += await asyncio.to_thread(stt.transcribe_segments, piece, name, t0)
                except Exception as exc:
                    if name == "same":
                        raise
                    log.warning("Modello di revisione %s non disponibile (%s): uso quello dell'ascolto", name, exc)
                    name = "same"
                    segments += await asyncio.to_thread(stt.transcribe_segments, piece, name, t0)
        return segments

    async def review(self, meta_file: Path, meta: dict) -> None:
        self.state, self.current = "revisione in corso", meta["id"]
        started = time.time()
        audio = await asyncio.to_thread(read_wav, meta_file.with_suffix(".wav"))
        profile = enhance.NoiseProfile()
        if meta.get("noise_profile"):
            profile.magnitude = np.array(meta["noise_profile"], dtype=np.float32)
        clean = await asyncio.to_thread(enhance.clean, audio, profile)
        segments = await self.transcribe(meta, clean)
        if segments is None:
            self.state = "interrotta: qualcuno sta parlando"
            return
        result = self.evaluate(meta, segments)
        result["took_s"] = round(time.time() - started, 1)
        self.learn(meta, segments, result)
        applied = tuning.observe(result)
        if applied:
            result["tuned"] = [{"key": a["key"], "value": a["value"], "why": a["why"]} for a in applied]
        meta.update(reviewed=True, reviewed_at=time.time())
        await asyncio.to_thread(self.store, meta_file, meta, result)
        self.state, self.current = "in attesa", ""
        log.info("Registrazione %s rivista in %.0fs: capito=%s attivazioni mancate=%d a vuoto=%d", meta["id"],
                 result["took_s"], result.get("agreement"), result["missed"], result["false_instant"])

    @staticmethod
    def evaluate(meta: dict, segments: list) -> dict:
        events = meta.get("events") or []
        rows = metrics.compare_transcripts(events, segments)
        audit = metrics.wake_audit(events, segments, has_wake)
        scores = [r["score"] for r in rows]
        worst = sorted((r for r in rows if r["score"] < metrics.LOW_AGREEMENT), key=lambda r: r["score"])[:3]
        return {"id": meta["id"], "at": time.time(), "started": meta["started"], "duration": meta.get("duration"),
                "voiced_s": meta.get("voiced_s"), "checked": len(rows), "events": len(events),
                "agreement": round(sum(scores) / len(scores), 3) if scores else None, "worst": worst,
                "review_text": " ".join(s["text"] for s in segments)[:400], **audit, **metrics.level_report(meta)}

    @staticmethod
    def learn(meta: dict, segments: list, result: dict) -> None:
        learner.on_review(result["missed"], result["false_instant"])
        if not result["missed"]:
            return
        for ev in meta.get("events") or []:
            if ev.get("kind") != "heard" or not ev.get("text"):
                continue
            first = TOKEN_RE.findall(ev["text"])[:1]
            if first and any(has_wake(s["text"]) and abs(s["start"] - float(ev["t"])) < 6 for s in segments):
                if learner.learn_variant(first[0]):
                    log.info("Dalla revisione ho imparato la variante «%s» di Atena", first[0])

    def store(self, meta_file: Path, meta: dict, result: dict) -> None:
        lines = [json.dumps(r, ensure_ascii=False) for r in recent_reviews(KEEP_REVIEWS - 1)]
        lines.append(json.dumps(result, ensure_ascii=False))
        atomic_write(REVIEWS, "\n".join(lines) + "\n")
        if earconf.number("ATENA_EAR_KEEP_REVIEWED_H", 2.0, 0.0, 48.0) <= 0:
            recorder.remove(meta_file)
        else:
            atomic_write(meta_file, json.dumps(meta, ensure_ascii=False))
        self.publish()

    def publish(self) -> None:
        rows = recent_reviews(SUMMARY_WINDOW)
        pending = sum(1 for _, m in recorder.listing() if not m.get("reviewed"))
        size = sum(f.stat().st_size for f in recorder.RECORDS.glob("*.wav")) if recorder.RECORDS.exists() else 0
        data = {"at": time.time(), "state": self.state, "recording": recorder.enabled(), "pending": pending,
                "disk_mb": round(size / 1048576, 1), "summary": metrics.summarize(rows), "tuning": tuning.snapshot(),
                "learned": learner.summary().get("variants", {}), "recent": rows[-8:]}
        try:
            atomic_write(SUMMARY, json.dumps(data, ensure_ascii=False))
        except OSError as exc:
            log.warning("Riepilogo dell'ascolto non salvato: %s", exc)
