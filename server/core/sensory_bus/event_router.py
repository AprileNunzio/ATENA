import logging
import asyncio
from typing import Callable, Awaitable, List

from server.core.event_sourcing.universal_space import UniversalObservation, UniversalAction
from server.features.continuous_learning.babbling_engine import babbling_engine

logger = logging.getLogger("atena.sensory_bus")

class SensoryBusCoordinator:
    """
    Ingresso unico per tutti gli stimoli sensoriali.
    Che si tratti di un frame della webcam, di un pacchetto di rete, o di audio,
    tutto passa da qui sotto forma di UniversalObservation.
    """
    def __init__(self):
        self.observation_queue: asyncio.Queue = asyncio.Queue()
        self.action_subscribers: List[Callable[[UniversalAction], Awaitable[None]]] = []
        self._running = False

    def start(self):
        if not self._running:
            self._running = True
            asyncio.create_task(self._process_queue())
            logger.info("Sensory Bus Coordinator avviato.")

    def stop(self):
        self._running = False

    async def push_observation(self, observation: UniversalObservation):
        """Invia un'osservazione universale nella coda del bus."""
        await self.observation_queue.put(observation)
        logger.debug(f"Observation {observation.id} [{observation.modality}] accodata.")

    async def emit_action(self, action: UniversalAction):
        """Invia un'azione astratta verso l'attuatore reale."""
        logger.info(f"Emissione Action {action.id} verso [{action.target_modality}].")
        for sub in self.action_subscribers:
            try:
                await sub(action)
            except Exception as e:
                logger.error(f"Errore nel subscriber dell'actuator per {action.target_modality}: {e}")

    def subscribe_to_actions(self, callback: Callable[[UniversalAction], Awaitable[None]]):
        """Registra un hardware driver o attuatore per ricevere comandi."""
        self.action_subscribers.append(callback)

    async def _process_queue(self):
        while self._running:
            observation: UniversalObservation = await self.observation_queue.get()
            try:
                # 1. Prova prima il Fast Path (System 1)
                # Nel sistema reale, si fa un check su semantic_cache
                logger.debug(f"Routing observation {observation.id} al System 1...")
                
                # Mock della logica di routing:
                # Se è un frame visivo di cui non sa nulla, andrà al BabblingEngine.
                # Per ora dirottiamo tutto quello che non è puro "text" di dominio noto
                # al motore esplorativo.
                if observation.modality in ["vision", "network_packet", "usb_interrupt", "unknown"]:
                    # Fallback al Motore di Esplorazione se il System 1 non ha mappe motorie pronte
                    await babbling_engine.handle_unknown_stimulus(observation, sensory_bus_ref=self)
                else:
                    # Passaggio normale al dispatcher
                    logger.debug(f"Gestione standard System 1 per {observation.modality}")
                    
            except Exception as e:
                logger.error(f"Errore durante l'elaborazione dell'Observation {observation.id}: {e}")
            finally:
                self.observation_queue.task_done()

sensory_bus = SensoryBusCoordinator()
