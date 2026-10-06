import logging
import asyncio

from server.core.event_sourcing.universal_space import UniversalAction
from server.core.sensory_bus.event_router import sensory_bus

logger = logging.getLogger("atena.actuator_gateway")

class UniversalActuatorGateway:
    """
    Traduttore fisico.
    Converte le UniversalAction (tensori/vettori/astrazioni) in segnali fisici 
    reali (HTTP, Seriale, Audio, OS Widgets).
    """
    def __init__(self):
        # Mappa dei driver di base hardcoded (Sistema 1 fisico)
        self.known_drivers = {
            "tts": self._route_tts,
            "network_packet": self._route_network,
            # "serial_usb": self._route_serial  # Da implementare con pyserial in futuro
        }

    def attach_to_bus(self):
        sensory_bus.subscribe_to_actions(self.handle_action)
        logger.info("Universal Actuator Gateway agganciato al Sensory Bus.")

    async def handle_action(self, action: UniversalAction):
        logger.debug(f"Gateway riceve Action {action.id} per modality [{action.target_modality}]")
        
        handler = self.known_drivers.get(action.target_modality)
        if handler:
            try:
                await handler(action)
            except Exception as e:
                logger.error(f"Errore hardware nel driver {action.target_modality}: {e}")
        else:
            # Fallback Dinamico: Il Babbling Engine ha generato un'azione per un hardware
            # di cui non abbiamo ancora scritto il driver nel dict known_drivers.
            logger.warning(f"Driver non trovato per {action.target_modality}. Tento iniezione generica (Raw Fuzzing)...")
            await self._generic_fuzzing_fallback(action)

    async def _route_tts(self, action: UniversalAction):
        # Nel sistema reale chiamerebbe tts_engine
        logger.info(f"[AUDIO OUT]: {action.control_vector}")
        
    async def _route_network(self, action: UniversalAction):
        """Traduce il vettore in una richiesta HTTP/TCP."""
        # Action.control_vector dovrebbe essere un dizionario es: {"url": "...", "method": "...", "payload": "..."}
        try:
            cv = action.control_vector if isinstance(action.control_vector, dict) else {}
            target_ip = action.target_id
            
            logger.info(f"[NETWORK OUT] Invio pacchetto a {target_ip} -> {cv}")
            # Mock del dispatch di rete per non crashare
            await asyncio.sleep(0.1) 
        except Exception as e:
            logger.error(f"Errore di rete: {e}")

    async def _generic_fuzzing_fallback(self, action: UniversalAction):
        """
        L'estremo tentativo. Se Atena non sa cos'è l'attuatore, logga i byte
        sperando di intercettare il device via OS-level hooks.
        """
        logger.critical(f"[RAW FUZZING OUT] Target: {action.target_id} | Vector: {action.control_vector}")
        # Qui potremmo agganciare un generatore di script dinamico (Skill Synthesis)
        # che prova a installare librerie python on-the-fly per usare la nuova periferica.

actuator_gateway = UniversalActuatorGateway()
