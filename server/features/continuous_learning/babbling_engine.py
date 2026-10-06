# flake8: noqa: E501
import logging
import asyncio
from typing import List, Dict

from server.core.event_sourcing.universal_space import (
    UniversalObservation,
    UniversalAction,
    RewardSignal,
)
from server.core.memory.semantic_cache import semantic_cache

logger = logging.getLogger("atena.babbling_engine")


class UniversalBabblingEngine:
    """
    Motore di esplorazione attiva (Motor/Social/Protocol Babbling).
    Quando Atena incontra un input sconosciuto (hardware o conversazionale),
    invece di fallire, genera "probe" (azioni esplorative sicure) e mappa
    le reazioni dell'ambiente per costruire un modello comportamentale da zero.
    """

    def __init__(self):
        self.active_explorations: Dict[str, bool] = {}

    async def handle_unknown_stimulus(
        self, observation: UniversalObservation, sensory_bus_ref=None
    ):
        """
        Punto di ingresso quando il System 1 non ha una risposta sicura (Cache Miss).
        Inizia il loop di Reinforcement Learning esplorativo.
        """
        source_id = observation.source_id
        if self.active_explorations.get(source_id):
            logger.debug(f"Esplorazione gia' in corso per la sorgente {source_id}.")
            return

        logger.warning(
            f"Stimolo sconosciuto rilevato da {source_id} (Modality: {observation.modality}). Avvio Babbling Engine."
        )
        self.active_explorations[source_id] = True

        try:
            # Fase 1: Il Sistema 2 elabora le Ipotesi e genera i Probe (Azioni sicure)
            probes = await self._generate_safe_probes(observation)

            # Fase 2: Loop di Esecuzione e Osservazione
            for probe_action in probes:
                logger.info(
                    f"Invio azione esplorativa {probe_action.id} verso {probe_action.target_id}..."
                )

                # Inviamo l'azione al Sensory Bus (che la instrada all'hardware o all'utente)
                if sensory_bus_ref:
                    await sensory_bus_ref.emit_action(probe_action)

                # Attendiamo la reazione dell'ambiente
                reaction_obs = await self._wait_for_reaction(
                    sensory_bus_ref, timeout=5.0
                )

                # Fase 3: Valutazione (Calcolo del Reward)
                reward = self._calculate_reward(probe_action, reaction_obs)
                logger.info(
                    f"Esito esplorazione: Reward = {reward.score}. Ragionamento: {reward.reasoning}"
                )

                # Fase 4: Consolidamento
                if reward.score > 0.5:
                    await self._commit_to_memory(observation, probe_action, reward)
                    logger.info(
                        f"Mappatura vincente memorizzata per la sorgente {source_id}."
                    )
                    break  # Abbiamo trovato un'azione valida, usciamo dal loop esplorativo

        except Exception as e:
            logger.error(f"Errore durante l'esplorazione del Babbling Engine: {e}")
        finally:
            self.active_explorations[source_id] = False
            logger.info(f"Babbling terminato per {source_id}.")

    async def _generate_safe_probes(
        self, observation: UniversalObservation
    ) -> List[UniversalAction]:
        """
        Usa il modello di esplorazione dedicato (Babbling Model) per generare azioni di test.
        Restituisce una lista di UniversalAction da provare.
        """
        from server.config.env import settings
        from server.features.llm_gateway.gateway import llm_gateway
        from server.features.llm_gateway.contracts import LLMRequest, LLMMessage
        import json

        logger.debug(
            f"Richiesta generazione probe al LLM di Babbling ({settings.BABBLING_MODEL}) per {observation.modality}..."
        )

        prompt = f"""
Sei il Babbling Engine di Atena. Hai ricevuto un segnale sconosciuto:
Modality: {observation.modality}
Source: {observation.source_id}
Dati: {observation.raw_data}

Genera 1 azione esplorativa (probe) sicura per testare la reazione.
Rispondi ESCLUSIVAMENTE con un JSON valido con questa struttura, senza alcun testo formattato o markdown:
{{"target_modality": "...", "target_id": "...", "control_vector": "...", "expected_observation_state": {{}}}}
"""
        req = LLMRequest(
            provider=settings.LLM_PROVIDER,
            model=settings.BABBLING_MODEL,
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.7,
            max_tokens=200,
        )

        try:
            res = await llm_gateway.generate(req)
            data = json.loads(res.content)
            return [
                UniversalAction(
                    target_modality=data.get("target_modality", "generic_actuator"),
                    target_id=data.get("target_id", observation.source_id),
                    control_vector=data.get("control_vector", ""),
                    expected_observation_state=data.get(
                        "expected_observation_state", {}
                    ),
                )
            ]
        except Exception as e:
            logger.warning(f"LLM Babbling fallito ({e}), fallback ai probe standard.")
            return [
                UniversalAction(
                    target_modality="generic_actuator",
                    target_id=observation.source_id,
                    control_vector=[0.0, 0.0, 0.0],
                    expected_observation_state={"state_changed": True},
                )
            ]

    async def _wait_for_reaction(
        self, sensory_bus_ref, timeout: float
    ) -> UniversalObservation:
        """Attende il frame/pacchetto/messaggio di ritorno."""
        # Simulazione attesa rete/sensore
        await asyncio.sleep(1.0)
        return UniversalObservation(
            modality="sensor_feedback",
            source_id="env",
            raw_data={"status": "ack", "sentiment": "positive"},
            metadata={"latency_ms": 120},
        )

    def _calculate_reward(
        self, action: UniversalAction, reaction: UniversalObservation
    ) -> RewardSignal:
        """
        Compara lo stato visivo/sensoriale ottenuto (reaction) con quello atteso dall'azione.
        """
        expected = action.expected_observation_state or {}
        actual = reaction.raw_data if isinstance(reaction.raw_data, dict) else {}

        # MOCK: Calcolo semplificato. Nel sistema reale qui si usa la Similarità Coseno
        # tra il Semantic Embedding dell'atteso e dell'ottenuto.
        score = 0.0
        reasoning = "Nessuna correlazione trovata."

        matches = sum(1 for k, v in expected.items() if actual.get(k) == v)
        if matches > 0 and len(expected) > 0:
            score = float(matches) / len(expected)
            reasoning = f"Correlazione trovata. Match: {matches}/{len(expected)}"

        return RewardSignal(
            action_id=action.id,
            observation_id=reaction.id,
            score=score,
            reasoning=reasoning,
        )

    async def _commit_to_memory(
        self,
        initial_stimulus: UniversalObservation,
        successful_action: UniversalAction,
        reward: RewardSignal,
    ):
        """
        Salva la transizione di stato [S -> A -> R] nel Deep Memory per il fine-tuning notturno.
        """
        logger.debug(
            f"Salvataggio pattern in memoria: Stimolo {initial_stimulus.id} -> Azione {successful_action.id}"
        )

        # Inserisce in cache semantica il pattern vincente (Hot-Path per il Sistema 1)
        # Questo permette ad Atena di non dover più 'esplorare' per questo esatto stimolo.
        await semantic_cache.record_success(
            query=str(initial_stimulus.raw_data),
            result_data={
                "action_vector": successful_action.control_vector,
                "reward_score": reward.score,
            },
        )


babbling_engine = UniversalBabblingEngine()
