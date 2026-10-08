from typing import List, Dict, Any
from fastapi import APIRouter
from server.features.cognitive_flow.flow_service import cognitive_flow_service

flow_router = APIRouter(prefix="/cognitive", tags=["cognitive"])

@flow_router.get("/flow/active", response_model=Dict[str, Any])
async def get_active_cognitive_flow() -> Dict[str, Any]:
    flow = cognitive_flow_service.get_active_flow()
    if not flow:
        flow = cognitive_flow_service.create_mock_flow_if_empty()
    return flow

@flow_router.get("/flow/history", response_model=List[Dict[str, Any]])
async def get_cognitive_flow_history(limit: int = 10) -> List[Dict[str, Any]]:
    flows = cognitive_flow_service.get_recent_flows(limit)
    if not flows:
        flows = [cognitive_flow_service.create_mock_flow_if_empty()]
    return flows
