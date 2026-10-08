import os
import logging
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from server.config.env import settings
from server.shared.errors.global_handler import register_global_error_handlers
from server.core.security_guard.zero_trust_interceptor import ZeroTrustMiddleware
from server.core.agent_registry.pool_manager import agent_pool
from server.features.home_assistant_bridge.ha_agent import HomeAssistantAgent
from server.features.vision_surveillance.surveillance_agent import VisionSurveillanceAgent
from server.features.self_healing_coder.coder_agent import SelfHealingCoderAgent
from server.features.analytic_agent.analytic_agent import AnalyticReasonerAgent
from server.features.parametric.designer_agent import ParametricDesignerAgent
from server.features.skill_synthesis.composition import dynamic_tools_agent, tool_builder_agent
from server.features.sysops_automation.sysops_agent import SysOpsAutomationAgent
from server.cmd.api_routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("atena.main")

def create_application() -> FastAPI:
    app = FastAPI(
        title="Atena Autonomous Cognitive Orchestrator",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ZeroTrustMiddleware)
    
    from server.shared.i18n.middleware import I18nMiddleware
    app.add_middleware(I18nMiddleware)

    register_global_error_handlers(app)

    try:
        from server.core.observability.telemetry import setup_telemetry
        setup_telemetry(app)
    except ImportError:
        logger.warning("Modulo Telemetry non trovato. Ignoro OpenTelemetry.")

    try:
        import server.features.agent_tools.maps_tool
        import server.features.agent_tools.web_search_tool
        import server.features.agent_tools.music_tool
        _ = server.features.agent_tools.music_tool
        _ = server.features.agent_tools.web_search_tool
        _ = server.features.agent_tools.maps_tool
        logger.info("Tool dinamici caricati e pronti all'uso.")
    except ImportError as e:
        logger.warning("Nessun tool dinamico caricato: %s", str(e))

    agent_pool.register_agent(HomeAssistantAgent())
    agent_pool.register_agent(VisionSurveillanceAgent())
    agent_pool.register_agent(SelfHealingCoderAgent())
    agent_pool.register_agent(SysOpsAutomationAgent())
    agent_pool.register_agent(AnalyticReasonerAgent())
    agent_pool.register_agent(ParametricDesignerAgent())
    agent_pool.register_agent(dynamic_tools_agent)
    agent_pool.register_agent(tool_builder_agent)
    logger.info("Core agents registered: %s", agent_pool.list_agents())

    try:
        from server.web.features.computer_control.api import router as computer_control_router
        app.include_router(computer_control_router)
        logger.info("Computer Control UI router caricato.")
    except Exception as e:
        logger.error("Errore nel caricare computer control UI: %s", str(e))

    app.include_router(router)

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        @app.get("/")
        async def serve_index():
            return FileResponse(str(web_dir / "index.html"))

        @app.get("/web")
        async def serve_web_page():
            return FileResponse(str(web_dir / "index.html"))

    @app.on_event("startup")
    async def on_startup() -> None:
        from server.features.music_library.scanner import music_organizer
        from server.core.sensory_bus.event_router import sensory_bus
        from server.core.sensory_bus.actuator_gateway import actuator_gateway
        import asyncio
        asyncio.create_task(music_organizer.scan_loop())
        sensory_bus.start()
        actuator_gateway.attach_to_bus()

        try:
            from server.core.db.database import engine, Base
            Base.metadata.create_all(bind=engine)
            logger.info("Database ORM Inizializzato (Tabelle sincronizzate).")
        except Exception as e:
            logger.error("Impossibile connettersi al database: %s", str(e))

        from server.core.cognitive_audit.embedding_engine import embedding_engine
        from server.core.context_graph.graph_client import graph_client

        model_ok = await embedding_engine.ensure_model_available()
        if not model_ok:
            logger.warning("Embedding model not found! Run: ollama pull nomic-embed-text")

        from server.core.orchestrator.interrupt_manager import project_manager
        project_manager.mark_interrupted_projects()

        logger.info(
            "Atena v2.0.0 online — %d agents, %d graph nodes, %d graph edges",
            len(agent_pool.list_agents()),
            graph_client.node_count(),
            graph_client.edge_count(),
        )

    @app.get("/health")
    async def health_check():
        from server.core.context_graph.graph_client import graph_client
        return {
            "status": "HEALTHY",
            "version": "2.0.0",
            "orchestrator": "ONLINE",
            "active_agents": agent_pool.list_agents(),
            "knowledge_graph": {
                "nodes": graph_client.node_count(),
                "edges": graph_client.edge_count(),
            },
            "upgrades": [
                "llm_intent_classifier",
                "react_reasoning_loop",
                "task_planner",
                "persistent_knowledge_graph",
                "real_embeddings",
                "skill_synthesis",
                "self_critique",
                "tool_protocol",
                "hardware_aware_onboarding",
                "semantic_fast_path_cache",
                "system1_non_autoregressive_router",
                "system2_latent_reasoning_engine",
                "realtime_streaming_web_interface",
            ],
        }

    return app

app = create_application()

if __name__ == "__main__":
    port_to_bind = int(os.environ.get("ATENA_PORT", getattr(settings, "ATENA_PORT", 80)))
    uvicorn.run(
        "server.cmd.main:app",
        host=settings.ATENA_HOST,
        port=port_to_bind,
        reload=(settings.ATENA_ENV == "development"),
    )
