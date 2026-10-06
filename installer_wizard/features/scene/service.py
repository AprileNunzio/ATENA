import asyncio
import logging
import time

from config import STATE_DIR
from atena_bus import BusError, Envelope, atena_bus

from features.scene.fusion import PresenceFusion
from features.scene.graph import SceneGraph

log = logging.getLogger("atena.scene")
STEP_EVERY = 2.0
CAPABILITIES = ["scene.where", "scene.readiness", "fusion.presence"]


def _publish(topic: str, payload: dict, retain: bool) -> None:
    try:
        atena_bus.publish(topic, payload, origin="scene", retain=retain)
    except BusError as exc:
        log.debug("Scena: %s non pubblicato: %s", topic, exc)


def _people_names() -> dict:
    try:
        from features.people import people
        return {p["slug"]: p.get("name") or p["slug"] for p in people.all_profiles(light=True) if p.get("slug")}
    except Exception:
        return {}


class Scene:
    def __init__(self) -> None:
        self._graph: SceneGraph | None = None
        self.fusion = PresenceFusion(_publish, names=_people_names)
        self.subscriptions = []

    @property
    def graph(self) -> SceneGraph:
        if self._graph is None:
            self._graph = SceneGraph(STATE_DIR / "scene.db")
        return self._graph

    def on_objects(self, envelope: Envelope) -> None:
        p = envelope.payload
        frame = p.get("frame") or [0, 0]
        holders = [x.get("name", "") for x in p.get("people", []) if x.get("known")]
        try:
            self.graph.observe(str(p.get("source") or "main"), list(p.get("objects") or []), (int(frame[0]), int(frame[1])),
                               holders[0] if holders else "")
        except (TypeError, ValueError, IndexError) as exc:
            log.debug("Scena: osservazione scartata: %s", exc)

    def start(self) -> None:
        if self.subscriptions:
            return
        self.subscriptions = [
            atena_bus.subscribe("vision.objects", self.on_objects),
            atena_bus.subscribe("vision.presence", lambda e: self.fusion.on_vision(e.payload)),
            atena_bus.subscribe("voice.speaker", lambda e: self.fusion.on_voice(e.payload)),
            atena_bus.subscribe("home.state_changed", lambda e: self.fusion.on_home(e.payload)),
            atena_bus.subscribe("fusion.arrival", self._arrival),
        ]

    @staticmethod
    def _arrival(envelope: Envelope) -> None:
        try:
            from features.habits.service import habits
            habits.foresee(arrival=True)
        except Exception as exc:
            log.debug("Previsione all'arrivo non avviata: %s", exc)

    async def run(self) -> None:
        self.start()
        last_announce = 0.0
        while True:
            try:
                self.fusion.step()
                if time.time() - last_announce > 30:
                    last_announce = time.time()
                    atena_bus.announce("scene", CAPABILITIES)
            except Exception as exc:
                log.warning("Scena: %s", exc)
            await asyncio.sleep(STEP_EVERY)


scene = Scene()
