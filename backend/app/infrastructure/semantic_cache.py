"""Redis-backed (with in-memory fallback) RBAC-aware Semantic Cache and Rate Limiter."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from typing import Any

from app.shared.cache import (
    NoOpRateLimiter,
    NoOpSemanticCache,
    RateLimiter,
    SemanticCache,
    SemanticCacheEntry,
    cosine_similarity,
)
from app.shared.config import Settings, get_settings

logger = logging.getLogger(__name__)


class RedisSemanticCache:
    """RBAC-partitioned semantic cache backed by Redis or an isolated in-memory store."""

    _KEY_PREFIX = "rag:scache:"

    def __init__(self, *, redis_client: Any = None, max_entries_per_bucket: int = 50) -> None:
        self._redis = redis_client
        self._max_entries_per_bucket = max(1, max_entries_per_bucket)
        # In-memory fallback store: bucket_key -> list[(expires_at, payload_dict)]
        self._memory: dict[str, list[tuple[float, dict[str, Any]]]] = {}

    @classmethod
    def _bucket_key(cls, permission_scope: str, active_version_snapshot: str) -> str:
        return f"{cls._KEY_PREFIX}{permission_scope}:{active_version_snapshot}"

    async def get(
        self,
        *,
        query_vector: Sequence[float],
        permission_scope: str,
        active_version_snapshot: str,
        threshold: float = 0.95,
    ) -> SemanticCacheEntry | None:
        bucket_key = self._bucket_key(permission_scope, active_version_snapshot)
        items: list[dict[str, Any]] = []

        if self._redis is not None:
            try:
                raw_list = await self._redis.lrange(bucket_key, 0, self._max_entries_per_bucket - 1)
                for raw in raw_list:
                    items.append(json.loads(raw))
            except Exception as exc:
                logger.debug("Redis semantic cache read failed: %s", exc)
                return None
        else:
            now = time.monotonic()
            bucket = self._memory.get(bucket_key, [])
            valid = [(exp, data) for exp, data in bucket if exp > now]
            self._memory[bucket_key] = valid
            items = [data for _, data in valid]

        best_entry: SemanticCacheEntry | None = None
        best_sim = -1.0
        for item in items:
            sim = cosine_similarity(query_vector, item.get("query_vector", ()))
            if sim >= threshold and sim > best_sim:
                best_sim = sim
                best_entry = SemanticCacheEntry(
                    query=item["query"],
                    query_vector=tuple(item["query_vector"]),
                    answer=item["answer"],
                    sources=item["sources"],
                    permission_scope=permission_scope,
                    active_version_snapshot=active_version_snapshot,
                    similarity=round(sim, 4),
                )
        return best_entry

    async def set(
        self,
        *,
        query: str,
        query_vector: Sequence[float],
        answer: str,
        sources: list[dict[str, Any]],
        permission_scope: str,
        active_version_snapshot: str,
        ttl_seconds: int = 3600,
    ) -> None:
        bucket_key = self._bucket_key(permission_scope, active_version_snapshot)
        payload = {
            "query": query,
            "query_vector": [float(v) for v in query_vector],
            "answer": answer,
            "sources": sources,
        }

        if self._redis is not None:
            try:
                await self._redis.lpush(bucket_key, json.dumps(payload, ensure_ascii=False))
                await self._redis.ltrim(bucket_key, 0, self._max_entries_per_bucket - 1)
                await self._redis.expire(bucket_key, max(1, ttl_seconds))
            except Exception as exc:
                logger.debug("Redis semantic cache write failed: %s", exc)
            return

        expires_at = time.monotonic() + max(1, ttl_seconds)
        bucket = self._memory.setdefault(bucket_key, [])
        bucket.insert(0, (expires_at, payload))
        del bucket[self._max_entries_per_bucket :]

    async def invalidate_all(self) -> None:
        self._memory.clear()
        if self._redis is not None:
            try:
                keys = await self._redis.keys(f"{self._KEY_PREFIX}*")
                if keys:
                    await self._redis.delete(*keys)
            except Exception as exc:
                logger.debug("Redis semantic cache invalidation failed: %s", exc)


class RedisRateLimiter:
    """Fixed-window per-user rate limiter backed by Redis or in-memory counters."""

    _KEY_PREFIX = "rag:rl:"

    def __init__(self, *, redis_client: Any = None) -> None:
        self._redis = redis_client
        self._memory: dict[str, tuple[int, float]] = {}

    async def allow(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
        if limit <= 0:
            return False
        full_key = f"{self._KEY_PREFIX}{key}"

        if self._redis is not None:
            try:
                count = await self._redis.incr(full_key)
                if count == 1:
                    await self._redis.expire(full_key, max(1, window_seconds))
                return int(count) <= limit
            except Exception as exc:
                logger.debug("Redis rate limiter failed open: %s", exc)
                return True

        now = time.monotonic()
        current_count, reset_at = self._memory.get(full_key, (0, now + window_seconds))
        if now >= reset_at:
            current_count = 0
            reset_at = now + window_seconds
        current_count += 1
        self._memory[full_key] = (current_count, reset_at)
        return current_count <= limit


def _try_create_redis_client(redis_url: str) -> Any:
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(redis_url, decode_responses=True)
    except Exception:
        return None


def get_semantic_cache(settings: Settings | None = None) -> SemanticCache:
    """Return configured SemanticCache or NoOpSemanticCache when disabled."""
    cfg = settings or get_settings()
    if not cfg.semantic_cache_enabled:
        return NoOpSemanticCache()
    return RedisSemanticCache(redis_client=_try_create_redis_client(cfg.redis_url))


def get_rate_limiter(settings: Settings | None = None) -> RateLimiter:
    """Return configured RateLimiter or NoOpRateLimiter when disabled."""
    cfg = settings or get_settings()
    if not cfg.rate_limit_enabled:
        return NoOpRateLimiter()
    return RedisRateLimiter(redis_client=_try_create_redis_client(cfg.redis_url))
