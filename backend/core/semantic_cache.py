"""Semantic Vector Caching Layer for Polaris.

Provides near-instant cache hits for semantically similar prompts using
vector cosine similarity matching (in-memory fast index or vector store).
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if len(vec_a) != len(vec_b) or not vec_a:
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


class SemanticCacheEntry:
    def __init__(
        self,
        prompt_text: str,
        embedding: List[float],
        response: Dict[str, Any],
        model: str,
        ttl_seconds: float = 3600.0,
    ) -> None:
        self.prompt_text = prompt_text
        self.embedding = embedding
        self.response = response
        self.model = model
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl_seconds


class SemanticCache:
    """In-memory vector cache with cosine similarity threshold."""

    def __init__(self, similarity_threshold: float = 0.95, max_entries: int = 1000) -> None:
        self.similarity_threshold = similarity_threshold
        self.max_entries = max_entries
        self._entries: List[SemanticCacheEntry] = []

    def lookup(
        self,
        query_embedding: List[float],
        target_model: str,
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        """Look for a cached response with cosine similarity >= threshold."""
        now = time.time()
        self._entries = [e for e in self._entries if e.expires_at > now]

        best_match: Optional[SemanticCacheEntry] = None
        highest_sim = 0.0

        for entry in self._entries:
            if entry.model != target_model:
                continue
            sim = _cosine_similarity(query_embedding, entry.embedding)
            if sim > highest_sim:
                highest_sim = sim
                best_match = entry

        if best_match and highest_sim >= self.similarity_threshold:
            return best_match.response, round(highest_sim, 4)

        return None

    def store(
        self,
        prompt_text: str,
        embedding: List[float],
        response: Dict[str, Any],
        model: str,
        ttl_seconds: float = 3600.0,
    ) -> None:
        """Store a new entry in the semantic cache."""
        if len(self._entries) >= self.max_entries:
            self._entries.pop(0)  # Simple FIFO eviction

        entry = SemanticCacheEntry(
            prompt_text=prompt_text,
            embedding=embedding,
            response=response,
            model=model,
            ttl_seconds=ttl_seconds,
        )
        self._entries.append(entry)

    def clear(self) -> None:
        self._entries.clear()
