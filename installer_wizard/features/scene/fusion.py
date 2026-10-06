import math
import threading
import time

PRIOR = -1.5
ARRIVE = 0.75
LEAVE = 0.3
PUBLISH_DELTA = 0.1
WEIGHTS = {"face": 3.0, "voice": 2.0, "home_tracker": 3.0}
HALF_LIFE = {"face": 60.0, "voice": 120.0, "home_tracker": 0.0}
SPOOF_FACTOR = 0.2


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class PresenceFusion:
    def __init__(self, publish, clock=time.time, names=None) -> None:
        self.publish = publish
        self.clock = clock
        self.names = names or (lambda: {})
        self.lock = threading.Lock()
        self.evidence: dict[str, dict[str, dict]] = {}
        self.labels: dict[str, str] = {}
        self.present: set[str] = set()
        self.last_published: dict[str, float] = {}
        self.context: dict = {}

    def add(self, slug: str, source: str, strength: float, name: str = "", detail: str = "", sign: int = 1) -> None:
        if not slug or source not in WEIGHTS:
            return
        with self.lock:
            self.evidence.setdefault(slug, {})[source] = {"w": sign * WEIGHTS[source] * max(0.0, min(1.0, strength)),
                                                          "at": self.clock(), "detail": detail[:60]}
            if name:
                self.labels[slug] = name[:60]

    def on_vision(self, payload: dict) -> None:
        for person in payload.get("people", []):
            if not person.get("known") or not person.get("slug"):
                continue
            strength = float(person.get("confidence") or 0)
            if (person.get("liveness") or {}).get("state") == "spoof":
                strength *= SPOOF_FACTOR
            self.add(person["slug"], "face", strength, person.get("name", ""), "camera")

    def on_voice(self, payload: dict) -> None:
        if payload.get("known"):
            self.add(str(payload.get("speaker") or ""), "voice", float(payload.get("score") or 0.8), detail=str(payload.get("device") or ""))

    def on_home(self, payload: dict) -> None:
        eid = str(payload.get("entity_id") or "")
        to = payload.get("to")
        if eid.startswith("person."):
            slug = self._slug_for(eid)
            if slug and to in ("home", "not_home"):
                self.add(slug, "home_tracker", 1.0, detail=eid, sign=1 if to == "home" else -1)
        elif eid.startswith("binary_sensor.") and to == "on":
            with self.lock:
                self.context["last_opening"] = {"entity": eid, "at": self.clock()}

    def _slug_for(self, eid: str) -> str:
        wanted = eid.split(".", 1)[1].replace("_", " ").split(" ")[0]
        for slug, name in {**self.names(), **self.labels}.items():
            if name.lower().split(" ")[0] == wanted or slug.split("-")[0] == wanted:
                return slug
        return ""

    def belief(self, slug: str, now: float) -> tuple[float, list[str]]:
        total, sources = PRIOR, []
        for source, ev in self.evidence.get(slug, {}).items():
            life = HALF_LIFE[source]
            decay = 1.0 if life == 0 else 0.5 ** ((now - ev["at"]) / life)
            if abs(ev["w"] * decay) >= 0.05:
                total += ev["w"] * decay
                sources.append(source)
        return _sigmoid(total), sorted(sources)

    def step(self) -> dict:
        now = self.clock()
        with self.lock:
            people, arrived, left = [], [], []
            for slug in list(self.evidence):
                p, sources = self.belief(slug, now)
                if slug not in self.present and p >= ARRIVE:
                    self.present.add(slug)
                    arrived.append(slug)
                elif slug in self.present and p <= LEAVE:
                    self.present.discard(slug)
                    left.append(slug)
                if not sources and slug not in self.present:
                    del self.evidence[slug]
                    continue
                people.append({"slug": slug, "name": self.labels.get(slug, slug), "probability": round(p, 3),
                               "present": slug in self.present, "sources": sources})
            changed = arrived or left or any(abs(x["probability"] - self.last_published.get(x["slug"], -1)) >= PUBLISH_DELTA for x in people)
            if changed:
                self.last_published = {x["slug"]: x["probability"] for x in people}
            snapshot = {"at": now, "people": sorted(people, key=lambda x: -x["probability"]), "context": dict(self.context)}
        if changed:
            self.publish("fusion.presence", snapshot, True)
        for slug in arrived:
            self.publish("fusion.arrival", {"slug": slug, "name": self.labels.get(slug, slug)}, False)
        for slug in left:
            self.publish("fusion.departure", {"slug": slug, "name": self.labels.get(slug, slug)}, False)
        return snapshot
