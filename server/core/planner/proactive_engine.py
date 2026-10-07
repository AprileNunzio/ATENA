import logging
from server.core.event_sourcing.universal_space import UniversalObservation
from server.features.llm_gateway.gateway import llm_gateway
from server.features.llm_gateway.contracts import LLMRequest, LLMMessage
from server.core.agent_registry.interfaces import AgentTaskRequest

logger = logging.getLogger("atena.proactive_engine")

class ProactiveEngine:
    """
    Analizza gli eventi sensoriali passivi per capire se Atena deve agire in modo proattivo.
    System 2 (Lento, Riflessivo, Autonomo).
    """
    def __init__(self, model_name="qwen2.5:7b"):
        self._model = model_name

    async def analyze_event(self, observation: UniversalObservation):
        if observation.modality != "home_assistant":
            return

        # Analizziamo se l'evento richiede un'azione
        entity = observation.source_id
        state = observation.raw_data.get("state")
        old_state = observation.metadata.get("old_state", {}).get("state")
        
        prompt = (
            f"Evento domotico rilevato: L'entità '{entity}' è passata da '{old_state}' a '{state}'.\n"
            "Sei il modulo di sicurezza e comfort proattivo (Jarvis).\n"
            "In base a questo evento, c'è un'azione logica o urgente che dovresti fare autonomamente?\n"
            "Esempi: se una finestra si apre e il riscaldamento è acceso, dovresti spegnerlo.\n"
            "Rispondi SOLO con un JSON: {\"requires_action\": true/false, \"reason\": \"...\", \"task_intent\": \"spegni il riscaldamento in quella stanza\"}"
        )

        try:
            res = await llm_gateway.generate_completion(
                LLMRequest(
                    model_name=self._model,
                    messages=[LLMMessage(role="user", content=prompt)],
                    temperature=0.1,
                    max_tokens=200,
                    component="proactive_engine"
                )
            )
            import json
            raw = res.content.strip()
            data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
            
            if data.get("requires_action"):
                logger.info(f"PROATTIVITA' INNESCATA: {data['reason']} -> Task: {data['task_intent']}")
                
                # Invia il task ad Home Assistant Agent
                from server.features.home_assistant_bridge.ha_agent import HomeAssistantAgent
                from server.core.kernel.consensus.instance import critical_jury
                agent = HomeAssistantAgent(jury=critical_jury)
                req = AgentTaskRequest(
                    task_id=f"proactive_{observation.id}",
                    intent="HOME_AUTOMATION",
                    raw_query=f"Azione proattiva necessaria: {data['task_intent']} (Motivo: {data['reason']})"
                )
                await agent.execute(req)
        except Exception as e:
            logger.error(f"Errore in analyze_event proattivo: {e}")

proactive_engine = ProactiveEngine()
