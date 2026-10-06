import os
import re
import math
import time
import json
import asyncio
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from server.config.env import settings

class CacheEntry(BaseModel):
    id: str
    query: str
    normalized_query: str
    embedding: List[float]
    action_result: Dict[str, Any]
    created_at: float
    hit_count: int = 0
    last_hit: float = 0.0

class CacheLookupResult(BaseModel):
    hit: bool
    similarity: float = 0.0
    action_result: Optional[Dict[str, Any]] = None
    cached_query: Optional[str] = None
    lookup_latency_ms: float = 0.0
    strategy: str = "miss"

class SemanticCache:
    def __init__(
        self,
        storage_path: Optional[str] = None,
        similarity_threshold: float = 0.90,
    ) -> None:
        self.storage_path = storage_path or os.path.join(settings.DATA_DIR, "semantic_cache.json")
        self.similarity_threshold = similarity_threshold
        self._entries: List[CacheEntry] = []
        self._exact_index: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._total_hits = 0
        self._total_lookups = 0
        self._load_from_disk()

    @staticmethod
    def _normalize(text: str) -> str:
        cleaned = re.sub(r"[^\w\s]", "", text.lower())
        return " ".join(cleaned.split())

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 <= 0.0 or norm2 <= 0.0:
            return 0.0
        return dot / (norm1 * norm2)

    def _load_from_disk(self) -> None:
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                for item in raw:
                    entry = CacheEntry(**item)
                    self._entries.append(entry)
                    self._exact_index[entry.normalized_query] = entry
        except Exception:
            pass

    def _save_to_disk(self) -> None:
        dir_name = os.path.dirname(self.storage_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
        try:
            data = [e.model_dump() for e in self._entries]
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def lookup_sync(
        self, query: str, query_embedding: Optional[List[float]] = None
    ) -> CacheLookupResult:
        start_time = time.perf_counter()
        self._total_lookups += 1
        normalized = self._normalize(query)

        if normalized in self._exact_index:
            entry = self._exact_index[normalized]
            entry.hit_count += 1
            entry.last_hit = time.time()
            self._total_hits += 1
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return CacheLookupResult(
                hit=True,
                similarity=1.0,
                action_result=entry.action_result,
                cached_query=entry.query,
                lookup_latency_ms=elapsed_ms,
                strategy="exact",
            )

        if query_embedding and self._entries:
            best_sim = 0.0
            best_entry: Optional[CacheEntry] = None
            for e in self._entries:
                sim = self._cosine_similarity(query_embedding, e.embedding)
                if sim > best_sim:
                    best_sim = sim
                    best_entry = e

            if best_sim >= self.similarity_threshold and best_entry is not None:
                best_entry.hit_count += 1
                best_entry.last_hit = time.time()
                self._total_hits += 1
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return CacheLookupResult(
                    hit=True,
                    similarity=best_sim,
                    action_result=best_entry.action_result,
                    cached_query=best_entry.query,
                    lookup_latency_ms=elapsed_ms,
                    strategy="semantic",
                )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return CacheLookupResult(
            hit=False,
            similarity=0.0,
            lookup_latency_ms=elapsed_ms,
            strategy="miss",
        )

    async def lookup(
        self, query: str, query_embedding: Optional[List[float]] = None
    ) -> CacheLookupResult:
        return self.lookup_sync(query, query_embedding)

    async def record_success(
        self,
        query: str,
        action_result: Dict[str, Any],
        embedding: Optional[List[float]] = None,
    ) -> CacheEntry:
        async with self._lock:
            normalized = self._normalize(query)
            if not embedding:
                try:
                    from server.core.cognitive_audit.embedding_engine import embedding_engine
                    embedding = await embedding_engine.embed(query)
                except Exception:
                    embedding = [0.0] * 128

            entry_id = f"entry_{len(self._entries) + 1}_{int(time.time())}"
            entry = CacheEntry(
                id=entry_id,
                query=query,
                normalized_query=normalized,
                embedding=embedding,
                action_result=action_result,
                created_at=time.time(),
                hit_count=0,
                last_hit=0.0,
            )

            if normalized in self._exact_index:
                old_entry = self._exact_index[normalized]
                self._entries.remove(old_entry)

            self._entries.append(entry)
            self._exact_index[normalized] = entry
            self._save_to_disk()
            return entry

    def clear(self) -> None:
        self._entries.clear()
        self._exact_index.clear()
        self._total_hits = 0
        self._total_lookups = 0
        if os.path.exists(self.storage_path):
            try:
                os.remove(self.storage_path)
            except Exception:
                pass

    def stats(self) -> Dict[str, Any]:
        hit_rate = (self._total_hits / self._total_lookups) if self._total_lookups > 0 else 0.0
        return {
            "entries_count": len(self._entries),
            "total_lookups": self._total_lookups,
            "total_hits": self._total_hits,
            "hit_rate": round(hit_rate, 4),
            "threshold": self.similarity_threshold,
        }

semantic_cache = SemanticCache()
