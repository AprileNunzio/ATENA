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
    # Memoria Ternaria per il 100% di Affidabilità: "verified", "pending", "invalid"
    validation_state: str = "verified"

class CacheLookupResult(BaseModel):
    hit: bool
    similarity: float = 0.0
    action_result: Optional[Dict[str, Any]] = None
    cached_query: Optional[str] = None
    lookup_latency_ms: float = 0.0
    strategy: str = "miss"
    validation_state: str = "miss"

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
        
        # Cache vettoriale per il 100% di Velocità (numpy)
        self._embedding_matrix = None
        self._np = None
        try:
            import numpy as np
            self._np = np
        except ImportError:
            pass
            
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

    def _rebuild_matrix(self):
        if self._np and self._entries:
            # Crea una matrice Nx128 normalizzata per L2
            mat = self._np.array([e.embedding for e in self._entries], dtype=self._np.float32)
            norms = self._np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1
            self._embedding_matrix = mat / norms
        else:
            self._embedding_matrix = None

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
            self._rebuild_matrix()
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
            self._rebuild_matrix()
        except Exception:
            pass

    def lookup_sync(
        self, query: str, query_embedding: Optional[List[float]] = None
    ) -> CacheLookupResult:
        start_time = time.perf_counter()
        self._total_lookups += 1
        normalized = self._normalize(query)

        # 1. Ricerca Esatta (O(1) Hash Map)
        if normalized in self._exact_index:
            entry = self._exact_index[normalized]
            
            # Affidabilità al 100%: Filtra allucinazioni precedentemente invalidate
            if entry.validation_state == "verified":
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
                    validation_state=entry.validation_state
                )

        # 2. Ricerca Semantica ad Alta Velocità (O(1) Matrice C-level)
        if query_embedding and self._entries:
            best_sim = 0.0
            best_entry = None
            
            if self._np is not None and self._embedding_matrix is not None:
                # Usa NumPy per calcolare tutte le similarity in una singola passata C++
                q_vec = self._np.array(query_embedding, dtype=self._np.float32)
                q_norm = self._np.linalg.norm(q_vec)
                if q_norm > 0:
                    q_vec = q_vec / q_norm
                    similarities = self._np.dot(self._embedding_matrix, q_vec)
                    best_idx = self._np.argmax(similarities)
                    best_sim_val = float(similarities[best_idx])
                    if best_sim_val >= self.similarity_threshold:
                        best_sim = best_sim_val
                        best_entry = self._entries[best_idx]
            else:
                # Fallback per cicli Python lenti se Numpy manca
                for e in self._entries:
                    sim = self._cosine_similarity(query_embedding, e.embedding)
                    if sim > best_sim:
                        best_sim = sim
                        best_entry = e

            if best_sim >= self.similarity_threshold and best_entry is not None:
                if best_entry.validation_state == "verified":
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
                        validation_state=best_entry.validation_state
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
