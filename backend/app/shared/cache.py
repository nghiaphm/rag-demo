"""RBAC-aware Semantic Cache and Rate Limiter port definitions."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.shared.auth import UserContext


@dataclass(frozen=True)
class SemanticCacheEntry:
    """Cached RAG answer partitioned by permission scope and document snapshot."""

    query: str
    query_vector: tuple[float, ...]
    answer: str
    sources: list[dict[str, Any]]
    permission_scope: str
    active_version_snapshot: str
    similarity: float = 1.0


def build_permission_scope(user: UserContext | None) -> str:
    """Compute a deterministic cache partition key for the user's RBAC scope."""
    if user is None:
        return "public"
    roles_part = ",".join(sorted(set(user.roles)))
    raw = f"user:{user.user_id}|roles:{roles_part}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def build_version_snapshot(active_version_ids: Sequence[str]) -> str:
    """Compute a deterministic hash representing the active document version set."""
    if not active_version_ids:
        return "empty"
    joined = "|".join(sorted(set(str(v) for v in active_version_ids)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Compute cosine similarity between two equal-length float vectors."""
    if not vec_a or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@runtime_checkable
class SemanticCache(Protocol):
    """Port for RBAC-partitioned semantic query caching."""

    async def get(
        self,
        *,
        query_vector: Sequence[float],
        permission_scope: str,
        active_version_snapshot: str,
        threshold: float = 0.95,
    ) -> SemanticCacheEntry | None:
        """Return a cached entry if similarity >= threshold within the exact permission & version scope."""

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
        """Store a response in the exact permission & version scope bucket."""

    async def invalidate_all(self) -> None:
        """Invalidate all cached entries (e.g., on document INDEXED or DELETE)."""


@runtime_checkable
class RateLimiter(Protocol):
    """Port for per-user / per-client bounded request rate limiting."""

    async def allow(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
        """Return True if the request is within budget, False if rate-limited."""


class NoOpSemanticCache:
    """Default no-op cache when semantic caching is disabled."""

    async def get(
        self,
        *,
        query_vector: Sequence[float],
        permission_scope: str,
        active_version_snapshot: str,
        threshold: float = 0.95,
    ) -> SemanticCacheEntry | None:
        return None

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
        return None

    async def invalidate_all(self) -> None:
        return None


class NoOpRateLimiter:
    """Default no-op rate limiter when rate limiting is disabled."""

    async def allow(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
        return True
