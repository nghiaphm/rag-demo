"""Prometheus operational metrics adapter enforcing strict low-cardinality labels."""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from app.shared.observability import MetricsRecorder

_ALLOWED_METHODS: frozenset[str] = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "OTHER"}
)
_ALLOWED_TRANSPORTS: frozenset[str] = frozenset({"json", "sse"})
_ALLOWED_MODES: frozenset[str] = frozenset({"stateless", "persistent"})
_ALLOWED_ROUTE_TYPES: frozenset[str] = frozenset({"rag", "document_tools", "agentic"})
_ALLOWED_STAGES: frozenset[str] = frozenset(
    {"rewrite", "multi_query", "retrieval", "rerank", "corrective", "sql", "generation"}
)
_ALLOWED_DIRECTIONS: frozenset[str] = frozenset({"input", "output"})


def _safe_outcome(outcome: str) -> str:
    cleaned = "".join(
        ch if (ch.isalnum() or ch in ("_", "-")) else "_"
        for ch in (outcome or "UNKNOWN").strip().upper()
    )
    return cleaned[:48] or "UNKNOWN"


class PrometheusMetricsRecorder(MetricsRecorder):
    """Wraps `prometheus_client` collectors with finite, low-cardinality label guards."""

    content_type: str = CONTENT_TYPE_LATEST

    def __init__(self, *, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry if registry is not None else CollectorRegistry()
        self._http_requests_total = Counter(
            "rag_http_requests_total",
            "Total completed HTTP requests partitioned by method, route template, and status code.",
            labelnames=("method", "route", "status_code"),
            registry=self.registry,
        )
        self._http_request_duration_seconds = Histogram(
            "rag_http_request_duration_seconds",
            "HTTP request latency in seconds partitioned by method, route template, and status code.",
            labelnames=("method", "route", "status_code"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0, 60.0, 120.0),
            registry=self.registry,
        )
        self._chat_turns_total = Counter(
            "rag_chat_turns_total",
            "Total chat turns partitioned by transport, mode, route_type, and bounded outcome.",
            labelnames=("transport", "mode", "route_type", "outcome"),
            registry=self.registry,
        )
        self._chat_ttft_seconds = Histogram(
            "rag_chat_ttft_seconds",
            "SSE time-to-first-content-delta in seconds.",
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
            registry=self.registry,
        )
        self._stage_duration_seconds = Histogram(
            "rag_stage_duration_seconds",
            "Execution duration of bounded RAG/Agent stages in seconds.",
            labelnames=("stage",),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0),
            registry=self.registry,
        )
        self._llm_tokens_total = Counter(
            "rag_llm_tokens_total",
            "Total LLM tokens consumed partitioned by direction (input or output).",
            labelnames=("direction",),
            registry=self.registry,
        )

    def record_http_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        norm_method = method.upper() if method and method.upper() in _ALLOWED_METHODS else "OTHER"
        norm_route = route if (route and route.startswith("/")) else "unmatched"
        norm_status = str(int(status_code))
        self._http_requests_total.labels(
            method=norm_method,
            route=norm_route,
            status_code=norm_status,
        ).inc()
        self._http_request_duration_seconds.labels(
            method=norm_method,
            route=norm_route,
            status_code=norm_status,
        ).observe(max(0.0, float(duration_seconds)))

    def record_chat_turn(
        self,
        *,
        transport: str,
        mode: str,
        route_type: str,
        outcome: str,
    ) -> None:
        norm_transport = transport.lower() if transport.lower() in _ALLOWED_TRANSPORTS else "json"
        norm_mode = mode.lower() if mode.lower() in _ALLOWED_MODES else "stateless"
        norm_route_type = (
            route_type.lower() if route_type.lower() in _ALLOWED_ROUTE_TYPES else "rag"
        )
        self._chat_turns_total.labels(
            transport=norm_transport,
            mode=norm_mode,
            route_type=norm_route_type,
            outcome=_safe_outcome(outcome),
        ).inc()

    def record_chat_ttft(self, *, duration_seconds: float) -> None:
        self._chat_ttft_seconds.observe(max(0.0, float(duration_seconds)))

    def record_stage_duration(self, *, stage: str, duration_seconds: float) -> None:
        if stage not in _ALLOWED_STAGES:
            return
        self._stage_duration_seconds.labels(stage=stage).observe(max(0.0, float(duration_seconds)))

    def record_llm_tokens(self, *, direction: str, count: int) -> None:
        if direction not in _ALLOWED_DIRECTIONS or count <= 0:
            return
        self._llm_tokens_total.labels(direction=direction).inc(int(count))

    def render(self) -> bytes:
        """Render current metrics registry in Prometheus text exposition format."""
        return generate_latest(self.registry)
