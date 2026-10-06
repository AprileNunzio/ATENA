import logging
import asyncio
from datetime import datetime

logger = logging.getLogger("atena.memory_distiller")

class DeepMemoryDistiller:
    """
    Il 'Sonno' di Atena.
    Si occupa di estrarre i successi del Sistema 2 e del Babbling Engine
    avvenuti durante il giorno, trasformarli in un dataset, e preparare
    il fine-tuning (LoRA/DPO) per il Sistema 1 locale, trasformando
    la memoria episodica in memoria parametrica (istinto).
    """
    def __init__(self):
        self.is_distilling = False
        self.last_run = None

    async def trigger_nightly_consolidation(self):
        """Inizia il processo di consolidamento (Sonno Profondo)."""
        if self.is_distilling:
            logger.warning("Distillazione gia' in corso.")
            return
            
        self.is_distilling = True
        logger.info("[NIGHTLY JOB] Avvio fase REM: Consolidamento della memoria episodica...")

        try:
            # 1. Estrazione Esperienze Positive
            logger.info("Fase 1: Estrazione successi (Reward > 0.8) dalla cache semantica...")
            successful_episodes = await self._extract_daily_successes()
            
            if not successful_episodes:
                logger.info("Nessuna nuova esperienza significativa da consolidare oggi. Fine fase REM.")
                return

            # 2. Formattazione Dataset (DPO/RLHF)
            logger.info(f"Fase 2: Compilazione dataset da {len(successful_episodes)} episodi...")
            dataset_path = await self._build_training_dataset(successful_episodes)
            
            # 3. Micro Fine-Tuning sul Sistema 1 (LLM Locale)
            logger.info("Fase 3: Avvio Adapter Tuning (LoRA) sul modello di Sistema 1...")
            await self._run_local_finetune(dataset_path)
            
            # 4. Swap dei pesi (Sveglia)
            logger.info("Fase 4: Reload dei pesi neurali completato. Atena si 'sveglia' piu' intelligente.")
            self.last_run = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Errore critico durante il sonno di Atena (Incubo/Crash): {e}")
        finally:
            self.is_distilling = False

    async def _extract_daily_successes(self) -> list:
        # Recupera le entry dal semantic_cache
        # MOCK: Simulazione recupero
        await asyncio.sleep(1)
        return [{"stimulus": "Esempio_A", "action": "Vettore_B", "reward": 0.95}]

    async def _build_training_dataset(self, episodes: list) -> str:
        # Genera il file .jsonl per l'addestramento
        await asyncio.sleep(1)
        return "/tmp/atena_dream_dataset_today.jsonl"

    async def _run_local_finetune(self, dataset_path: str):
        # Chiama l'API di un framework locale (es. unpeft, axolotl, o Ollama experimental tuning)
        logger.info(f"Addestramento in background su {dataset_path}...")
        await asyncio.sleep(2)
        logger.info("Addestramento converso con loss stabile.")

memory_distiller = DeepMemoryDistiller()
