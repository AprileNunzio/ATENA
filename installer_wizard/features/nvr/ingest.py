import asyncio
import json
import logging
import ssl
import time

log = logging.getLogger("atena.nvr.ingest")
MAX_MESSAGE = 64 * 1024


def parse_event(raw: bytes, now: float | None = None) -> dict | None:
    if len(raw) > MAX_MESSAGE:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    after = data.get("after") if isinstance(data.get("after"), dict) else data
    camera, label = after.get("camera"), after.get("label")
    if not isinstance(camera, str) or not isinstance(label, str) or not camera or not label:
        return None
    if data.get("type") not in (None, "new", "update", "end"):
        return None
    try:
        score = float(after.get("top_score") or after.get("score") or 0.0)
        at = float(after.get("start_time") or now or time.time())
    except (TypeError, ValueError):
        return None
    zones = after.get("current_zones") or after.get("entered_zones") or []
    zone = ", ".join(str(z) for z in zones[:4]) if isinstance(zones, list) else ""
    event_id = str(after.get("id") or f"{camera}-{label}-{int(at)}")
    return {"id": f"mqtt:{event_id}"[:80], "at": at, "camera": camera[:80], "label": label.lower()[:40],
            "score": max(0.0, min(1.0, score)), "source": "mqtt", "zone": zone[:80],
            "text": str(after.get("sub_label") or "")[:120], "final": data.get("type") == "end"}


class MqttIngest:
    def __init__(self, on_event) -> None:
        self.on_event = on_event
        self.state = "disabled"
        self.detail = ""
        self.received = 0
        self.task: asyncio.Task | None = None
        self.signature = ""

    @staticmethod
    def available() -> bool:
        try:
            import aiomqtt
        except ImportError:
            return False
        return bool(aiomqtt)

    def configure(self, settings: dict) -> None:
        signature = json.dumps({k: settings.get(k) for k in ("enabled", "mqtt_host", "mqtt_port", "mqtt_topic", "mqtt_user",
                                                             "mqtt_password", "mqtt_tls")}, sort_keys=True)
        if signature == self.signature and self.task and not self.task.done():
            return
        self.signature = signature
        self.stop()
        if not settings.get("enabled") or not settings.get("mqtt_host"):
            self.state, self.detail = "disabled", ""
            return
        if not self.available():
            self.state, self.detail = "missing_dependency", "aiomqtt"
            return
        self.task = asyncio.get_running_loop().create_task(self._loop(dict(settings)))

    def stop(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = None

    async def _loop(self, settings: dict) -> None:
        import aiomqtt
        delay = 2.0
        while True:
            self.state = "connecting"
            try:
                tls = ssl.create_default_context() if settings.get("mqtt_tls") else None
                async with aiomqtt.Client(hostname=settings["mqtt_host"], port=int(settings["mqtt_port"]),
                                          username=settings.get("mqtt_user") or None,
                                          password=settings.get("mqtt_password") or None,
                                          tls_context=tls, identifier=f"atena-nvr-{int(time.time())}") as client:
                    await client.subscribe(settings["mqtt_topic"])
                    self.state, self.detail, delay = "connected", "", 2.0
                    async for message in client.messages:
                        event = parse_event(bytes(message.payload or b""))
                        if event:
                            self.received += 1
                            self.on_event(event)
            except asyncio.CancelledError:
                self.state = "disabled"
                raise
            except Exception as exc:
                self.state, self.detail = "error", type(exc).__name__
                log.warning("NVR: connessione MQTT non riuscita (%s), nuovo tentativo tra %.0f s", type(exc).__name__, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 120.0)
