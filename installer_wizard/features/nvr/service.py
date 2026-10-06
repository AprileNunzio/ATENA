import asyncio
import logging
import re
import time

from atena_bus import BusError, Envelope, atena_bus

from features.nvr import settings as nvr_settings
from features.nvr.ingest import MqttIngest
from features.nvr.search import parse
from features.nvr.store import EventStore

log = logging.getLogger("atena.nvr")
STATUS_EVERY = 30.0
PRUNE_EVERY = 3600.0
CAPABILITIES = ["nvr.events", "nvr.search", "nvr.mqtt_ingest"]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", str(text).lower()).strip("_")[:40] or "camera"


class Nvr:
    def __init__(self) -> None:
        self.settings = nvr_settings.load()
        self._store: EventStore | None = None
        self.ingest = MqttIngest(self.record)
        self.subscription = None

    @property
    def store(self) -> EventStore:
        if self._store is None:
            self._store = EventStore(nvr_settings.NVR_DIR / "events.db")
        return self._store

    def record(self, event: dict) -> bool:
        if event["label"] not in self.settings["labels"] or event["score"] < self.settings["min_score"]:
            return False
        if not self.store.add(event):
            return False
        payload = {k: event[k] for k in ("id", "at", "camera", "label", "score", "source", "zone", "text")}
        try:
            atena_bus.publish(f"nvr.event.{slug(event['camera'])}", payload, origin="nvr")
            if event["label"] in self.settings["notify_labels"]:
                atena_bus.publish("nvr.alert", payload, origin="nvr")
        except BusError as exc:
            log.debug("NVR: evento non pubblicato: %s", exc)
        return True

    def on_camera_event(self, envelope: Envelope) -> None:
        p = envelope.payload
        try:
            at = float(p.get("at") or envelope.ts)
        except (TypeError, ValueError):
            return
        self.record({"id": f"cam:{str(p.get('source', ''))[:40]}:{at:.3f}", "at": at, "camera": str(p.get("name") or p.get("source") or "?"),
                     "label": str(p.get("kind") or "motion"), "score": 1.0, "source": "camera", "zone": "", "text": str(p.get("text") or "")})

    def update_settings(self, body: dict) -> dict:
        fresh = nvr_settings.validate(body, self.settings)
        nvr_settings.save(fresh)
        self.settings = fresh
        try:
            self.ingest.configure(fresh)
        except RuntimeError:
            pass
        self.publish_status()
        return nvr_settings.public(fresh)

    def search(self, text: str, limit: int = 50) -> dict:
        query = parse(text)
        return {"query": {"since": query.since, "until": query.until, "labels": sorted(query.labels), "terms": list(query.terms)},
                "events": self.store.search(query, limit)}

    def cameras(self) -> list[dict]:
        try:
            from features.cameras import live
            from features.cameras.cameras import CAM_DIR, cameras
            from features.cameras.recorder import recorder
        except Exception:
            return []
        out = []
        for row in live.listing():
            cid = row["id"][2:] if row["id"].startswith("c-") else ""
            cam = cameras.items.get(cid, {}) if cid else {}
            folder = CAM_DIR / cid if cid else None
            segments = list(folder.glob("seg_*.mp4")) if folder and folder.exists() else []
            out.append({"id": row["id"], "name": row["name"], "kind": row["kind"], "room": row.get("room", ""),
                        "stream": bool(row.get("stream")), "recording": cid in recorder.procs,
                        "record_enabled": bool(cam and cameras._recording(cam)), "retention_min": cam.get("retention_min", 0),
                        "segments": len(segments), "bytes": sum(s.stat().st_size for s in segments if s.exists())})
        return out

    def status(self) -> dict:
        since = time.time() - 86400
        return {"ingest": {"state": self.ingest.state, "detail": self.ingest.detail, "received": self.ingest.received,
                           "available": self.ingest.available()},
                "counts_24h": self.store.counts(since), "settings": nvr_settings.public(self.settings)}

    def publish_status(self) -> None:
        try:
            atena_bus.publish("nvr.status", self.status(), origin="nvr", retain=True)
        except BusError as exc:
            log.debug("NVR: stato non pubblicato: %s", exc)

    async def run(self) -> None:
        self.subscription = atena_bus.subscribe("camera.event.>", self.on_camera_event)
        self.ingest.configure(self.settings)
        last_prune = 0.0
        while True:
            try:
                atena_bus.announce("nvr", CAPABILITIES, info={"ingest": self.ingest.state})
                self.publish_status()
                if time.time() - last_prune > PRUNE_EVERY:
                    last_prune = time.time()
                    removed = await asyncio.to_thread(self.store.prune, self.settings["retention_days"])
                    if removed:
                        log.info("NVR: rimossi %d eventi oltre la conservazione", removed)
            except Exception as exc:
                log.warning("NVR: %s", exc)
            await asyncio.sleep(STATUS_EVERY)


nvr = Nvr()
