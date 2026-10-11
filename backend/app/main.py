"""FastAPI entrypoint.

Expose RAG pipeline (Phase 4) qua HTTP API. API layer chỉ validate và gọi service.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.api import chat, documents
from app.cloud_connections import CloudConnections
from app.config import settings
from app.document_indexes import initialize_document_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo/đóng cloud clients mà không thay đổi PostgreSQL pipeline hiện tại."""
    cloud_connections = CloudConnections(settings)
    app.state.cloud_connections = cloud_connections
    statuses = await run_in_threadpool(cloud_connections.connect_all)
    if statuses["mongodb"].ok:
        await run_in_threadpool(
            initialize_document_indexes,
            cloud_connections.mongodb.database,
        )
    try:
        yield
    finally:
        await run_in_threadpool(cloud_connections.close)


app = FastAPI(title="RAG Demo API", version="0.1.0", lifespan=lifespan)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Health check xác nhận app khởi động và config load được."""
    return {"status": "ok", "llm_model": settings.llm_model}


@app.get("/health/dependencies", tags=["system"])
async def dependency_health() -> JSONResponse:
    """Readiness cloud an toàn; không trả endpoint, database name hay credentials."""
    statuses = await run_in_threadpool(app.state.cloud_connections.connect_all)
    content = {
        "status": "ok" if all(item.ok for item in statuses.values()) else "degraded",
        "dependencies": {name: item.to_dict() for name, item in statuses.items()},
    }
    return JSONResponse(status_code=200 if content["status"] == "ok" else 503, content=content)
