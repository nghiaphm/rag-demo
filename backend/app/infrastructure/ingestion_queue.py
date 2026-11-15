"""ARQ/Redis adapter for asynchronous document ingestion queueing."""

from __future__ import annotations

from typing import Any

from app.documents.ports import IngestionQueue, IngestionQueueError


class NoOpIngestionQueue(IngestionQueue):
    """Disabled queue used when ASYNC_INGESTION_ENABLED=false."""

    async def enqueue_ingestion(self, *, version_id: str, job_id: str) -> str | None:
        return None


class ArqIngestionQueue(IngestionQueue):
    """Enqueues ingestion jobs into Redis via ARQ."""

    def __init__(
        self,
        *,
        redis_url: str,
        pool_factory: Any = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool_factory = pool_factory
        self._pool: Any = None

    async def _get_pool(self) -> Any:
        if self._pool is not None:
            return self._pool
        if self._pool_factory is not None:
            self._pool = await self._pool_factory(self._redis_url)
            return self._pool
        try:
            from arq import create_pool
            from arq.connections import RedisSettings
        except ImportError as exc:
            raise IngestionQueueError(
                "Cần cài đặt 'arq' và 'redis' để bật async ingestion."
            ) from exc
        try:
            self._pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
        except Exception as exc:
            raise IngestionQueueError("Không thể kết nối Redis ingestion queue.") from exc
        return self._pool

    async def enqueue_ingestion(self, *, version_id: str, job_id: str) -> str | None:
        pool = await self._get_pool()
        try:
            job = await pool.enqueue_job(
                "process_ingestion_job",
                version_id,
                job_id,
                _job_id=job_id,
            )
        except Exception as exc:
            raise IngestionQueueError("Không thể đưa job ingestion vào hàng đợi.") from exc
        return getattr(job, "job_id", job_id)

    async def close(self) -> None:
        pool = self._pool
        self._pool = None
        if pool is None:
            return
        close_fn = getattr(pool, "aclose", None) or getattr(pool, "close", None)
        if close_fn is None:
            return
        result = close_fn()
        if hasattr(result, "__await__"):
            await result


def get_ingestion_queue(settings: Any) -> IngestionQueue:
    """Create configured IngestionQueue adapter (disabled by default)."""
    if not getattr(settings, "async_ingestion_enabled", False):
        return NoOpIngestionQueue()
    return ArqIngestionQueue(redis_url=settings.redis_url)
