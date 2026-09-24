"""FastAPI entrypoint.

Expose RAG pipeline (Phase 4) qua HTTP API. API layer chỉ validate và gọi service.
"""

from fastapi import FastAPI

from app.api import chat, documents
from app.config import settings

app = FastAPI(title="RAG Demo API", version="0.1.0")
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Health check xác nhận app khởi động và config load được."""
    return {"status": "ok", "llm_model": settings.llm_model}
