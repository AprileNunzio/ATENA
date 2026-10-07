import math
import httpx

from config import ollama_url
from features.team import roster

class ToolRouter:
    def __init__(self) -> None:
        self.embeddings_cache: dict[str, list[float]] = {}
        self._indexing = False

    async def get_embedding(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{ollama_url()}/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": text},
                    timeout=5.0
                )
                if res.status_code == 200:
                    return res.json().get("embedding", [])
        except Exception:
            pass
        return []

    def cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        if not v1 or not v2:
            return 0.0
        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm_a = math.sqrt(sum(a * a for a in v1))
        norm_b = math.sqrt(sum(b * b for b in v2))
        return dot_product / (norm_a * norm_b) if norm_a and norm_b else 0.0

    async def index_tools(self) -> None:
        if self._indexing:
            return
        self._indexing = True
        try:
            for agent_id in roster.ids():
                if agent_id not in self.embeddings_cache:
                    profile = roster.profile(agent_id)
                    tool_names = " ".join(t["name"] for t in profile.get("tools", []))
                    doc = f"{profile.get('name', '')} {profile.get('description', '')} {tool_names}"
                    emb = await self.get_embedding(doc)
                    if emb:
                        self.embeddings_cache[agent_id] = emb
        finally:
            self._indexing = False

    async def retrieve(self, user_prompt: str, top_k: int = 7) -> set[str]:
        if not self.embeddings_cache:
            await self.index_tools()
            
        prompt_emb = await self.get_embedding(user_prompt)
        if not prompt_emb:
            return set(roster.ids())  # Fallback to all agents if embedding fails
            
        scores = []
        for agent_id, agent_emb in self.embeddings_cache.items():
            score = self.cosine_similarity(prompt_emb, agent_emb)
            scores.append((score, agent_id))
            
        scores.sort(key=lambda x: x[0], reverse=True)
        
        # Core agents that should always be present
        core_agents = {"laws", "home_assistant", "mind", "understanding", "team", "capabilities"}
        retrieved = set(agent_id for _, agent_id in scores[:top_k])
        
        return core_agents.union(retrieved)

tool_router = ToolRouter()
