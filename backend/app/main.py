"""FastAPI entrypoint.

Expose RAG pipeline (Phase 4) qua HTTP API. API layer chỉ validate và gọi service.
"""

from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, chat, documents, sessions
from app.infrastructure.connections import CloudConnections, is_readiness_ok
from app.infrastructure.ingestion_queue import get_ingestion_queue
from app.infrastructure.logging_config import configure_logging
from app.infrastructure.metrics import PrometheusMetricsRecorder
from app.infrastructure.observability import get_tracer
from app.infrastructure.semantic_cache import get_rate_limiter, get_semantic_cache
from app.shared.config import Settings, settings
from app.shared.observability import (
    get_metrics_recorder,
    reset_request_id,
    set_metrics_recorder,
    set_request_id,
    validate_or_generate_request_id,
)
from app.conversations.indexes import initialize_conversation_indexes
from app.documents.indexes import initialize_document_indexes

configure_logging(settings)
_default_metrics_recorder = PrometheusMetricsRecorder()
set_metrics_recorder(_default_metrics_recorder)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo/đóng MongoDB Atlas và Qdrant Cloud clients dùng chung."""
    cloud_connections = CloudConnections(settings)
    app.state.cloud_connections = cloud_connections
    app.state.tracer = get_tracer(settings)
    app.state.semantic_cache = get_semantic_cache(settings)
    app.state.rate_limiter = get_rate_limiter(settings)
    app.state.ingestion_queue = get_ingestion_queue(settings)
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
        await app.state.ingestion_queue.close()
        app.state.tracer.flush()
        await run_in_threadpool(cloud_connections.close)


class SecurityHeadersMiddleware:
    """Pure ASGI middleware attaching safe HTTP security headers without buffering streams."""

    _HEADERS: tuple[tuple[bytes, bytes], ...] = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
    )

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def _send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                existing = {name.lower() for name, _ in headers}
                for key, val in self._HEADERS:
                    if key not in existing:
                        headers.append((key, val))
                message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, _send_with_headers)


class RequestObservabilityMiddleware:
    """Pure ASGI middleware validating X-Request-ID and recording low-cardinality HTTP metrics."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        raw_req_id: str | None = None
        for h_name, h_val in scope.get("headers") or ():
            if h_name.lower() == b"x-request-id":
                try:
                    raw_req_id = h_val.decode("latin-1")
                except Exception:
                    raw_req_id = None
                break

        req_id = validate_or_generate_request_id(raw_req_id)
        token = set_request_id(req_id)
        started_at = time.perf_counter()
        status_code = 500

        async def _send_with_request_id(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 200))
                headers = [
                    (k, v)
                    for k, v in (message.get("headers") or [])
                    if k.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", req_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self._app(scope, receive, _send_with_request_id)
        finally:
            elapsed = max(0.0, time.perf_counter() - started_at)
            route_obj = scope.get("route")
            route_template = getattr(route_obj, "path", None) or "unmatched"
            if getattr(settings, "metrics_enabled", True):
                try:
                    get_metrics_recorder().record_http_request(
                        method=str(scope.get("method", "OTHER")),
                        route=route_template,
                        status_code=status_code,
                        duration_seconds=elapsed,
                    )
                except Exception:
                    pass
            reset_request_id(token)


def configure_middlewares(target_app: FastAPI, app_settings: Settings = settings) -> None:
    """Attach dynamic CORS, HTTP security headers, and request observability middlewares."""
    target_app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=(
            ["Content-Type", "Authorization", "X-Request-ID"]
            if app_settings.auth_enabled
            else ["Content-Type", "X-Request-ID"]
        ),
        expose_headers=["X-Request-ID"],
    )
    target_app.add_middleware(SecurityHeadersMiddleware)
    target_app.add_middleware(RequestObservabilityMiddleware)


app = FastAPI(title="RAG Demo API", version="0.1.0", lifespan=lifespan)
configure_middlewares(app, settings)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(sessions.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Health check xác nhận app khởi động và config load được."""
    return {"status": "ok", "llm_model": settings.llm_model}


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint() -> Response:
    """Prometheus scrape endpoint (excluded from OpenAPI to preserve DTO parity)."""
    if not getattr(settings, "metrics_enabled", True):
        raise HTTPException(status_code=404, detail="Metrics disabled.")
    active = get_metrics_recorder()
    renderer = getattr(active, "render", None)
    content = renderer() if callable(renderer) else _default_metrics_recorder.render()
    content_type = getattr(active, "content_type", _default_metrics_recorder.content_type)
    return Response(content=content, media_type=content_type)


@app.get("/health/dependencies", tags=["system"])
async def dependency_health() -> JSONResponse:
    """Readiness cloud an toàn; không trả endpoint, database name hay credentials."""
    checker = (
        getattr(app.state.cloud_connections, "check_health_all", None)
        or app.state.cloud_connections.connect_all
    )
    statuses = await run_in_threadpool(checker)
    healthy = is_readiness_ok(statuses, settings)
    content = {
        "status": "ok" if healthy else "degraded",
        "dependencies": {name: item.to_dict() for name, item in statuses.items()},
    }
    return JSONResponse(status_code=200 if healthy else 503, content=content)
