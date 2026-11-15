"""ARQ worker handling asynchronous document ingestion jobs.

Run with:
    arq app.workers.ingestion_worker.WorkerSettings
from the ``backend/`` directory.
"""

from __future__ import annotations

import logging
from typing import Any

from anyio import to_thread

from app.documents.ingestion import create_ingestion_service
from app.infrastructure.connections import CloudConnections
from app.infrastructure.semantic_cache import get_semantic_cache
from app.shared.config import settings

logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize shared MongoDB, Qdrant, and SemanticCache resources for worker jobs."""
    connections = CloudConnections(settings)
    statuses = await to_thread.run_sync(connections.connect_all)
    if not statuses["mongodb"].ok or not statuses["qdrant"].ok:
        logger.warning("Worker started with degraded cloud dependencies: %s", statuses)
    ctx["cloud_connections"] = connections
    ctx["semantic_cache"] = get_semantic_cache(settings)


async def shutdown(ctx: dict[str, Any]) -> None:
    """Flush and close worker connections cleanly."""
    connections = ctx.get("cloud_connections")
    if connections is not None:
        await to_thread.run_sync(connections.close)


def _resolve_ingestion_service(ctx: dict[str, Any]):
    service = ctx.get("ingestion_service")
    if service is not None:
        return service
    connections = ctx.get("cloud_connections")
    database = getattr(getattr(connections, "mongodb", None), "database", None)
    qdrant_client = getattr(getattr(connections, "qdrant", None), "client", None)
    if database is None or qdrant_client is None:
        raise RuntimeError("Worker cloud dependencies chưa sẵn sàng.")
    return create_ingestion_service(database=database, qdrant_client=qdrant_client)


async def process_ingestion_job(
    ctx: dict[str, Any],
    version_id: str,
    job_id: str,
) -> dict[str, Any]:
    """Execute parse -> chunk -> embed -> upsert Qdrant -> activate for a queued version."""
    ingestion_service = _resolve_ingestion_service(ctx)
    result = await to_thread.run_sync(ingestion_service.process_version, version_id, job_id)

    semantic_cache = ctx.get("semantic_cache")
    if semantic_cache is not None:
        try:
            await semantic_cache.invalidate_all()
        except Exception:
            logger.warning("Failed to invalidate semantic cache after async ingestion", exc_info=True)

    return {
        "document_id": result.document_id,
        "version_id": result.version_id,
        "job_id": result.job_id,
        "num_chunks": result.num_chunks,
        "activated": result.activated,
        "status": result.status.value,
    }


def _redis_settings_from_env():
    try:
        from arq.connections import RedisSettings
    except ImportError:
        return None
    return RedisSettings.from_dsn(settings.redis_url)


class WorkerSettings:
    """ARQ worker entrypoint configuration."""

    functions = [process_ingestion_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings_from_env()
    max_jobs = 4
    job_timeout = 600
