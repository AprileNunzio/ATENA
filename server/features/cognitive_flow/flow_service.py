from typing import List, Dict, Any, Optional
from server.core.telemetry.journey import journey, Journey

class CognitiveFlowService:
    @staticmethod
    def get_active_flow() -> Optional[Dict[str, Any]]:
        active = journey.active()
        if active:
            return active.snapshot()
        recent = journey.recent()
        if recent:
            return recent[0]
        return None

    @staticmethod
    def get_recent_flows(limit: int = 10) -> List[Dict[str, Any]]:
        items = journey.recent()
        return items[:limit]

    @staticmethod
    def create_mock_flow_if_empty() -> Dict[str, Any]:
        existing = journey.active() or (journey.recent()[0] if journey.recent() else None)
        if existing:
            return existing.snapshot() if isinstance(existing, Journey) else existing

        j = journey.begin("Analisi meteo e diagnostica di sistema", "operatore_locale")
        with journey.span("laws", "Leggi Fondamentali", "Verifica Asimov & Zero-Trust") as h1:
            h1.ok("Nessuna violazione riscontrata")
        with journey.span("cache", "Memoria Semantica Cache", "Ricerca vettoriale embedding nomic") as h2:
            h2.fail("Cache miss (similarita 0.62 < 0.88)")
        with journey.span("router", "System 1 Router", "Analisi riflessiva non-autoregressiva") as h3:
            h3.ok("Instradamento verso Swarm Agenti")
        with journey.span("classifier", "Classificatore Intenti", "Intent: TELEMETRY_DIAGNOSTICS") as h4:
            h4.ok("Score: 0.96")
        with journey.span("agent", "SysOps Automation Agent", "Interrogazione metriche hardware e rete", parallel=True) as h5:
            h5.note("CPU: 12% | RAM: 42% | Sensorica: OK")
            h5.ok("Metriche raccolte con successo")
        with journey.span("reasoning", "System 2 Latent Engine", "Sintesi cognitiva e verifica coerenza") as h6:
            h6.note("Pensiero logico: stato nominale, nessun intervento di auto-healing richiesto.")
            h6.ok("Sintesi validata")
        journey.finish("Sistema Atena pienamente operativo. Tutti i nodi cognitivi rispondono con latenza <50ms.", "SUCCESS", "agent_sysops")
        return j.snapshot()

cognitive_flow_service = CognitiveFlowService()
