from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class FlowNode(BaseModel):
    id: int
    parent: Optional[int] = None
    kind: str
    name: str
    state: str
    started_at: float
    ended_at: Optional[float] = None
    detail: str = ""

class FlowEdge(BaseModel):
    source: int
    target: int
    edge_type: str = "flow"
    label: str = ""

class CognitiveJourneySnapshot(BaseModel):
    id: str
    query: str
    who: str = ""
    state: str
    answer: str = ""
    agent: str = ""
    started: float
    elapsed: float
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[List[Any]] = Field(default_factory=list)
