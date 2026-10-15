"""FastAPI entrypoint.

Expose RAG pipeline (Phase 4) qua HTTP API. API layer chỉ validate và gọi service.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, documents, sessions
from app.cloud_connections import CloudConnections
from app.config import settings
from app.conversation_indexes import initialize_conversation_indexes
from app.document_indexes import initialize_document_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo/đóng MongoDB Atlas và Qdrant Cloud clients dùng chung."""
    cloud_connections = CloudConnections(settings)
    app.state.cloud_connections = cloud_connections
    statuses = await run_in_threadpool(cloud_connections.connect_all)
    if statuses["mongodb"].ok:
        await run_in_threadpool(
            initialize_document_indexes,
            cloud_connections.mongodb.database,
        )
        await run_in_threadpool(
            initialize_conversation_indexes,
            cloud_connections.mongodb.database,
        )
    try:
        yield
    finally:
        await run_in_threadpool(cloud_connections.close)


app = FastAPI(title="RAG Demo API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # Exact development origins; localhost and 127.0.0.1 are distinct origins.
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(sessions.router)


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
