import base64
import json
from typing import Dict, Any, AsyncGenerator
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from server.core.orchestrator.dispatcher import orchestrator_dispatcher
from server.core.context_graph.graph_client import graph_client
from server.core.security_guard.token_provider import token_provider
from server.features.voice_biometrics.tts_engine import tts_engine
from server.features.voice_biometrics.audio_contracts import TTSRequest
from server.features.mesh_coordinator.p2p_mesh import p2p_mesh
from server.features.mesh_coordinator.mesh_models import PeerNode
from server.core.memory.semantic_cache import semantic_cache
from server.core.orchestrator.system1_router import system1_router, System1Intent
from server.core.reasoning.system2_engine import system2_engine
from server.core.onboarding.hardware_detector import hardware_detector
from server.core.onboarding.setup_wizard import onboarding_wizard, OnboardingConfig
from server.core.telemetry.journey import journey
from server.features.weather.weather_controller import weather_router
from server.features.presence_privacy.presence_controller import presence_router, system_router, privacy_router
from server.features.cognitive_flow.flow_controller import flow_router

router = APIRouter(prefix="/api/v1")
router.include_router(weather_router)
router.include_router(presence_router)
router.include_router(system_router)
router.include_router(privacy_router)
router.include_router(flow_router)

class AuthExchangeRequest(BaseModel):
    client_id: str
    client_secret: str
    device_type: str

class UserCommandPayload(BaseModel):
    query: str
    device_id: str = "web_console"
    voice_pcm_base64: str = ""
    context: Dict[str, Any] = {}

class StreamReasoningPayload(BaseModel):
    query: str
    context: Dict[str, Any] = {}

class KnowledgeNodePayload(BaseModel):
    id: str
    node_type: str
    label: str
    properties: Dict[str, Any] = {}

class KnowledgeEdgePayload(BaseModel):
    source_id: str
    target_id: str
    relation_type: str = "CONNECTED_TO"
    weight: float = 1.0

class CameraFeedPayload(BaseModel):
    device_id: str
    frame_base64: str
    timestamp: float

LOOPBACK = {"127.0.0.1", "::1", "localhost"}

async def _stream_reasoning_generator(query: str, context: Dict[str, Any]) -> AsyncGenerator[str, None]:
    cached = await semantic_cache.lookup(query)
    if cached.hit and cached.action_result:
        yield f"event: cache_hit\ndata: {json.dumps({'speech_output': cached.action_result.get('speech_output', ''), 'similarity': cached.similarity, 'latency_ms': cached.lookup_latency_ms, 'strategy': cached.strategy})}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': 'completed', 'source': 'semantic_cache'})}\n\n"
        return

    decision = await system1_router.classify(query)
    yield f"event: system1\ndata: {json.dumps(decision.model_dump())}\n\n"

    if decision.intent != System1Intent.COMPLEX_TASK:
        res = await orchestrator_dispatcher.dispatch_user_command(
            raw_query=query,
            speaker_id="web_user",
            device_id="web_console",
            biometric_score=0.95,
            context_override=context,
        )
        active_j = journey.active()
        if active_j:
            yield f"event: journey_snapshot\ndata: {json.dumps(active_j.snapshot())}\n\n"
        yield f"event: response\ndata: {json.dumps({'chunk': res.speech_output, 'surface': res.result_data.get('surface'), 'action': res.result_data.get('action')})}\n\n"
        await semantic_cache.record_success(query, {
            "agent_id": res.agent_id,
            "speech_output": res.speech_output,
            "result_data": res.result_data,
        })
        yield f"event: done\ndata: {json.dumps({'status': 'completed', 'source': decision.intent.value})}\n\n"
        return

    j = journey.begin(query, "web_user")
    j.step("router", "System 1 Router", f"Intent: {decision.intent.value}", "ok")
    yield f"event: status\ndata: {json.dumps({'step': 'system2_activated'})}\n\n"
    yield f"event: journey_snapshot\ndata: {json.dumps(j.snapshot())}\n\n"
    accumulated_thinking = ""
    accumulated_response = ""

    async for chunk in system2_engine.stream_execute(query, context):
        if chunk.chunk_type == "thinking":
            accumulated_thinking += chunk.content
            yield f"event: thinking\ndata: {json.dumps({'chunk': chunk.content})}\n\n"
        elif chunk.chunk_type == "response":
            accumulated_response += chunk.content
            yield f"event: response\ndata: {json.dumps({'chunk': chunk.content})}\n\n"
        elif chunk.chunk_type == "status":
            yield f"event: status\ndata: {json.dumps({'step': chunk.content})}\n\n"

    if accumulated_thinking:
        j.step("reasoning", "System 2 Latent Reasoning", accumulated_thinking[:400], "ok")
    if accumulated_response:
        j.finish("ok", accumulated_response, "system2_latent_engine")
        yield f"event: journey_snapshot\ndata: {json.dumps(j.snapshot())}\n\n"
        await semantic_cache.record_success(query, {
            "agent_id": "system2_latent_engine",
            "speech_output": accumulated_response,
            "thinking": accumulated_thinking,
        })

    yield f"event: done\ndata: {json.dumps({'status': 'completed', 'source': 'system2_latent'})}\n\n"

@router.post("/stream/reasoning")
async def stream_reasoning_endpoint_post(payload: StreamReasoningPayload) -> StreamingResponse:
    return StreamingResponse(
        _stream_reasoning_generator(payload.query, payload.context),
        media_type="text/event-stream",
    )

@router.get("/stream/reasoning")
async def stream_reasoning_endpoint_get(query: str = "") -> StreamingResponse:
    return StreamingResponse(
        _stream_reasoning_generator(query, {}),
        media_type="text/event-stream",
    )

@router.get("/onboarding/profile")
async def get_onboarding_profile() -> Dict[str, Any]:
    return hardware_detector.detect().model_dump()

@router.post("/onboarding/setup")
async def execute_onboarding_setup(payload: OnboardingConfig) -> Dict[str, Any]:
    return await onboarding_wizard.execute_setup(payload)

@router.get("/memory/cache/stats")
async def get_semantic_cache_stats() -> Dict[str, Any]:
    return semantic_cache.stats()

@router.post("/memory/cache/clear")
async def clear_semantic_cache() -> Dict[str, Any]:
    semantic_cache.clear()
    return {"status": "cleared"}

@router.post("/auth/exchange")
async def exchange_token(payload: AuthExchangeRequest, request: Request) -> Dict[str, Any]:
    if not request.client or request.client.host not in LOOPBACK:
        raise HTTPException(status_code=403, detail="Token rilasciati solo al supervisore locale")
    token = token_provider.issue_token(
        subject=payload.client_id,
        claims={"device_type": payload.device_type, "role": "OPERATOR"},
    )
    return {"status": "success", "token": token}

@router.post("/command")
async def handle_user_command(payload: UserCommandPayload) -> Dict[str, Any]:
    speaker_id = "user_primary"
    biometric_score = 0.95

    if payload.voice_pcm_base64:
        raw_pcm = base64.b64decode(payload.voice_pcm_base64)
        if len(raw_pcm) > 0:
            pass

    response = await orchestrator_dispatcher.dispatch_user_command(
        raw_query=payload.query,
        speaker_id=speaker_id,
        device_id=payload.device_id,
        biometric_score=biometric_score,
        context_override=payload.context or None,
    )

    p2p_mesh.commit_state_event({
        "event_type": "USER_COMMAND_EXECUTED",
        "task_id": response.task_id,
        "agent": response.agent_id,
        "status": response.status,
    })

    return {
        "status": "success",
        "task_id": response.task_id,
        "agent_id": response.agent_id,
        "speech_output": response.speech_output,
        "execution_time_ms": response.execution_time_ms,
        "result_data": response.result_data,
    }

@router.get("/knowledge/graph")
async def get_knowledge_graph_snapshot() -> Dict[str, Any]:
    snapshot = graph_client.export_snapshot()
    return {"status": "success", "graph": snapshot.model_dump()}

@router.post("/knowledge/node")
async def upsert_knowledge_node(payload: KnowledgeNodePayload) -> Dict[str, Any]:
    from server.core.context_graph.node_schema import NodeType
    try:
        node_type = NodeType(payload.node_type)
    except ValueError:
        return {"status": "error", "message": f"Tipo di nodo non valido: {payload.node_type}"}
    graph_client.upsert_node(
        node_id=payload.id,
        node_type=node_type,
        label=payload.label,
        properties=payload.properties,
    )
    return {"status": "success", "id": payload.id}

@router.post("/knowledge/edge")
async def link_knowledge_nodes(payload: KnowledgeEdgePayload) -> Dict[str, Any]:
    from server.core.context_graph.node_schema import RelationType
    try:
        relation = RelationType(payload.relation_type)
    except ValueError:
        return {"status": "error", "message": f"Tipo di relazione non valido: {payload.relation_type}"}
    try:
        graph_client.link_nodes(payload.source_id, payload.target_id, relation, payload.weight)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "success"}

@router.post("/tts/synthesize")
async def synthesize_speech(payload: TTSRequest) -> Response:
    wav_bytes = tts_engine.synthesize_speech_wav(payload)
    return Response(content=wav_bytes, media_type="audio/wav")

@router.post("/mesh/sync")
async def sync_mesh_network(peer: PeerNode) -> Dict[str, Any]:
    p2p_mesh.register_peer(peer)
    sync_data = p2p_mesh.get_sync_payload()
    return {"status": "success", "sync": sync_data.model_dump()}

from server.core.sensory_bus.event_router import sensory_bus
from server.core.event_sourcing.universal_space import UniversalObservation

@router.post("/vision/feed")
async def receive_camera_feed(payload: CameraFeedPayload) -> Dict[str, Any]:
    # Wrappiamo il feed nell'Universal Space e lo gettiamo nel bus
    obs = UniversalObservation(
        modality="vision",
        source_id=payload.device_id,
        raw_data=payload.frame_base64,
        metadata={"timestamp": payload.timestamp}
    )
    await sensory_bus.push_observation(obs)
    
    return {
        "status": "success",
        "device_id": payload.device_id,
        "processed": True,
        "bus_event_id": obs.id
    }

@router.get("/i18n/languages")
async def get_supported_languages() -> Dict[str, Any]:
    from server.shared.i18n.config import discover_languages
    from pathlib import Path
    server_langs = set(discover_languages("server"))
    installer_path = Path("installer_wizard")
    if installer_path.exists():
        for p in installer_path.rglob("*.json"):
            if p.parent.name == "language":
                server_langs.add(p.stem)
    return {"languages": sorted(server_langs), "default": "it"}

@router.websocket("/ws/stream")
async def websocket_stream_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("query", "")
            if query:
                res = await orchestrator_dispatcher.dispatch_user_command(
                    raw_query=query,
                    speaker_id="stream_user",
                    device_id=data.get("device_id", "stream_device"),
                    biometric_score=0.9,
                )
                await websocket.send_json({
                    "event": "COMMAND_RESULT",
                    "speech_output": res.speech_output,
                    "agent_id": res.agent_id,
                })
    except WebSocketDisconnect:
        pass
