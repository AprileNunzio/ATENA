import asyncio
import json
import logging
import websockets
from server.config.env import settings
from server.core.event_sourcing.universal_space import UniversalObservation
from server.core.sensory_bus.event_router import sensory_bus

logger = logging.getLogger("atena.ha_sensory_driver")

class HomeAssistantSensoryDriver:
    """
    Ascolta il WebSocket di Home Assistant in tempo reale e converte
    gli eventi (es. cambi di stato, movimento, temperatura) in UniversalObservation
    sul SensoryBus di Atena, rendendo il sistema PROATTIVO anziché reattivo.
    """
    def __init__(self, ws_url: str = None, token: str = settings.HOME_ASSISTANT_TOKEN):
        # Es: "ws://192.168.1.100:8123/api/websocket"
        base = settings.HOME_ASSISTANT_URL.replace("http://", "ws://").replace("https://", "wss://")
        self._ws_url = ws_url or f"{base}/api/websocket"
        self._token = token
        self._running = False
        self._msg_id = 1

    async def start(self):
        if not self._token:
            logger.warning("Token HA mancante, driver HA WebSocket non avviato.")
            return
        
        self._running = True
        logger.info(f"Connessione a HA WebSocket: {self._ws_url}")
        
        while self._running:
            try:
                async with websockets.connect(self._ws_url) as ws:
                    await self._authenticate(ws)
                    await self._subscribe_events(ws)
                    await self._listen_loop(ws)
            except Exception as e:
                logger.error(f"Errore connessione HA WebSocket: {e}. Ritento in 5s...")
                await asyncio.sleep(5)

    def stop(self):
        self._running = False

    async def _authenticate(self, ws):
        # HA invia subito un auth_required
        msg = json.loads(await ws.recv())
        if msg.get("type") == "auth_required":
            await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
            auth_ok = json.loads(await ws.recv())
            if auth_ok.get("type") != "auth_ok":
                raise Exception(f"HA Auth fallita: {auth_ok}")
            logger.info("HA WebSocket Autenticato")

    async def _subscribe_events(self, ws):
        await ws.send(json.dumps({
            "id": self._msg_id,
            "type": "subscribe_events",
            "event_type": "state_changed"
        }))
        self._msg_id += 1

    async def _listen_loop(self, ws):
        async for message in ws:
            if not self._running:
                break
            
            data = json.loads(message)
            if data.get("type") == "event" and data["event"].get("event_type") == "state_changed":
                event_data = data["event"]["data"]
                entity_id = event_data.get("entity_id", "")
                new_state = event_data.get("new_state", {})
                
                # Filtra entità rumorose se necessario (es. sensori tempo)
                if entity_id.startswith("sensor.time"):
                    continue
                
                # Invia al SensoryBus
                obs = UniversalObservation(
                    modality="home_assistant",
                    source_id=entity_id,
                    raw_data=new_state,
                    metadata={"old_state": event_data.get("old_state")}
                )
                await sensory_bus.push_observation(obs)
                logger.debug(f"HA Event spinto nel bus: {entity_id} -> {new_state.get('state')}")

ha_driver = HomeAssistantSensoryDriver()
