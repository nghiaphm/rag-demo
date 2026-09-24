"""
FastAPI entrypoint.

Phase 0 chỉ dựng app ở mức foundation: khởi động được và có health check.
Chưa có endpoint RAG (`/documents`, `/chat`) — các phase sau mới thêm.
"""

from fastapi import FastAPI

from app.config import settings

app = FastAPI(title="RAG Demo API", version="0.0.1")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Health check xác nhận app khởi động và config load được."""
    return {"status": "ok", "llm_model": settings.llm_model}
