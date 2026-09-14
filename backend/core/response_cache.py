"""Response Caching Layer for Polaris.

Provides fast exact-match lookup for LLM responses to reduce latency,
save provider quota, and avoid duplicate API calls.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any, Dict, Optional, Tuple

from core.coordination import CoordinationError
from core.routing_coordination import (
    CACHE_SCOPE_EXACT,
    CacheKind,
    RoutingCoordinationAdapter,
)
from core.state_store import InMemoryStateStore


def generate_cache_key(
    model: str,
    payload: Dict[str, Any],
    stream: bool = False,
) -> str:
    """Generate a deterministic SHA-256 hash key for a given request payload."""
    request_payload = payload.get("request")
    if not isinstance(request_payload, dict):
        request_payload = payload
    normalized_data = {
        "model": str(model).strip().lower(),
        "stream": bool(stream),
        "messages": request_payload.get("messages", []),
        "contents": request_payload.get("contents", []),
        "prompt": request_payload.get("prompt", ""),
        "system_instruction": request_payload.get("system_instruction")
        or request_payload.get("systemInstruction"),
        "temperature": request_payload.get("temperature"),
        "top_p": request_payload.get("top_p"),
        "max_tokens": request_payload.get("max_tokens") or request_payload.get("max_output_tokens"),
        "generation_config": request_payload.get("generationConfig"),
        "tools": request_payload.get("tools"),
    }

    # Dump deterministically sorted JSON string
    serialized = json.dumps(normalized_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ResponseCache:
    """In-memory cache with TTL and LRU expiration."""

    def __init__(self, default_ttl_seconds: int = 3600, max_entries: int = 1000) -> None:
        self.default_ttl_seconds = max(1, default_ttl_seconds)
        self.max_entries = max(1, max_entries)
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a cached response if valid and unexpired."""
        if key not in self._cache:
            self.misses += 1
            return None

        expires_at, data = self._cache[key]
        if time.time() > expires_at:
            self._cache.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        return data

    def set(self, key: str, data: Any, ttl_seconds: Optional[int] = None) -> None:
        """Store a response in cache with TTL."""
        ttl = (
            ttl_seconds
            if (ttl_seconds is not None and ttl_seconds > 0)
            else self.default_ttl_seconds
        )
        expires_at = time.time() + ttl

        # Evict oldest entry if capacity is reached
        if len(self._cache) >= self.max_entries and key not in self._cache:
            first_key = next(iter(self._cache))
            self._cache.pop(first_key, None)

        self._cache[key] = (expires_at, data)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def delete(self, key: str) -> None:
        """Remove one local entry without changing hit/miss counters."""
        self._cache.pop(key, None)

    def size(self) -> int:
        """Return the count of unexpired items."""
        now = time.time()
        # Clean expired
        expired = [k for k, (exp, _) in self._cache.items() if now > exp]
        for k in expired:
            self._cache.pop(k, None)
        return len(self._cache)


class CoordinatedResponseCache:
    """Local response bytes gated by fenced shared metadata and generation."""

    scope = CACHE_SCOPE_EXACT

    def __init__(
        self,
        local_cache: ResponseCache,
        coordination: RoutingCoordinationAdapter,
    ) -> None:
        if not isinstance(local_cache, ResponseCache):
            raise ValueError("A local response cache is required.")
        if coordination is None:
            raise ValueError("Cache coordination is required.")
        self._local = local_cache
        self._coordination = coordination

    def configure_coordination(self, coordination: RoutingCoordinationAdapter) -> None:
        """Replace coordination only at a lifecycle boundary and discard local bytes."""

        if coordination is None:
            raise ValueError("Cache coordination is required.")
        self._local.clear()
        self._coordination = coordination

    @staticmethod
    def content_digest(content: bytes, media_type: str) -> str:
        if not isinstance(content, bytes) or not isinstance(media_type, str):
            raise ValueError("Cache content is invalid.")
        media = media_type.encode("utf-8")
        digest = hashlib.sha256()
        digest.update(len(media).to_bytes(4, "big"))
        digest.update(media)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        return digest.hexdigest()

    @staticmethod
    def _media_kind(media_type: str) -> str:
        normalized = str(media_type or "").lower()
        if "json" in normalized:
            return "json"
        if normalized.startswith("text/"):
            return "text"
        return "binary"

    async def get(self, key: str) -> Optional[Tuple[bytes, str]]:
        try:
            generation = await self._coordination.current_generation(self.scope)
            metadata = await self._coordination.resolve_cache_metadata(
                CacheKind.EXACT,
                key,
                generation=generation,
            )
        except CoordinationError:
            self._local.delete(key)
            return None
        if metadata is None:
            self._local.delete(key)
            return None
        local = self._local.get(key)
        if local is None and metadata.content is not None and metadata.media_type is not None:
            local = (metadata.content, metadata.media_type)
            self._local.set(key, local)
        if (
            not isinstance(local, tuple)
            or len(local) != 2
            or not isinstance(local[0], bytes)
            or not isinstance(local[1], str)
        ):
            self._local.delete(key)
            return None
        content, media_type = local
        if (
            self.content_digest(content, media_type) != metadata.content_digest
            or self._media_kind(media_type) != metadata.media_kind
        ):
            self._local.delete(key)
            return None
        try:
            if await self._coordination.current_generation(self.scope) != generation:
                self._local.delete(key)
                return None
        except CoordinationError:
            self._local.delete(key)
            return None
        return content, media_type

    async def set(
        self,
        key: str,
        value: Tuple[bytes, str],
        ttl_seconds: int,
    ) -> bool:
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or not isinstance(value[0], bytes)
            or not isinstance(value[1], str)
        ):
            raise ValueError("Cache content is invalid.")
        content, media_type = value
        self._local.set(key, value, ttl_seconds)
        try:
            generation = await self._coordination.current_generation(self.scope)
            await self._coordination.publish_cache_metadata(
                CacheKind.EXACT,
                key,
                content_digest=self.content_digest(content, media_type),
                media_kind=self._media_kind(media_type),
                generation=generation,
                ttl_seconds=ttl_seconds,
                content=content,
                media_type=media_type,
            )
        except CoordinationError:
            self._local.delete(key)
            return False
        return True

    async def invalidate(self) -> int:
        self._local.clear()
        return await self._coordination.invalidate(self.scope)


# Global singleton instance
def _new_process_local_coordination() -> RoutingCoordinationAdapter:
    """Build a fresh standalone coordination boundary for cache metadata."""

    return RoutingCoordinationAdapter(
        InMemoryStateStore(),
        identifier_key=secrets.token_bytes(32),
        fencing_epoch=1,
    )


response_cache = ResponseCache()
response_cache_coordinator = CoordinatedResponseCache(
    response_cache,
    _new_process_local_coordination(),
)


def reset_response_cache_coordination() -> None:
    """Restore cache coordination after a runtime lifecycle is closed or aborted."""

    response_cache_coordinator.configure_coordination(_new_process_local_coordination())
