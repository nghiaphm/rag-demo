"""Observability port definitions and no-op fallback implementations.

This module lives in ``app.shared`` so domain, RAG, and chat modules can
instrument execution spans without depending on concrete tracing SDKs.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
import re
from types import TracebackType
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

_REQUEST_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,64}\Z")

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"gsk_[A-Za-z0-9_-]{8,}"), "gsk_[REDACTED]"),
    (re.compile(r"AIza[A-Za-z0-9_-]{8,}"), "AIza[REDACTED]"),
    (re.compile(r"(pk|sk)-lf-[A-Za-z0-9_-]{8,}"), r"\1-lf-[REDACTED]"),
    (re.compile(r"tvly-[A-Za-z0-9_-]{8,}"), "tvly-[REDACTED]"),
    (re.compile(r"sk-(?:proj-|svcacct-|ant-)?[A-Za-z0-9_-]{12,}"), "sk-[REDACTED]"),
    (re.compile(r"(mongodb(?:\+srv)?://)([^/\s@\"']+)@"), r"\1[REDACTED]@"),
    (re.compile(r"(redis(?:s)?://)([^/\s@\"']*)@"), r"\1[REDACTED]@"),
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1[REDACTED]"),
)

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def validate_or_generate_request_id(raw_value: str | None) -> str:
    """Validate incoming X-Request-ID against strict ASCII pattern or mint a clean UUIDv4."""
    if isinstance(raw_value, str) and raw_value.isascii() and _REQUEST_ID_RE.fullmatch(raw_value):
        return raw_value
    return str(uuid4())


def get_request_id() -> str | None:
    """Return active request correlation ID from contextvars."""
    return request_id_var.get()


def set_request_id(request_id: str | None) -> Token[str | None]:
    """Bind request correlation ID into contextvars and return reset token."""
    return request_id_var.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore previous request_id_var state."""
    request_id_var.reset(token)


def redact_secrets(text: str) -> str:
    """Mask known API key, Bearer token, and credential-bearing URI patterns in strings."""
    if not text:
        return text
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


@runtime_checkable
class SpanContext(Protocol):
    """Protocol representing an active execution span inside a trace."""

    def set_attribute(self, key: str, value: Any) -> None:
        """Attach a key-value attribute to the span."""

    def set_output(self, output: Any) -> None:
        """Record the output payload for the span."""

    def record_usage(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """Record token usage metrics on the span."""

    def record_error(self, error: BaseException | str) -> None:
        """Record an error or exception message on the span."""

    def __enter__(self) -> SpanContext:
        """Enter the span context manager."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the span context manager."""


@runtime_checkable
class TraceContext(Protocol):
    """Protocol representing a top-level request trace."""

    def span(
        self,
        name: str,
        *,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanContext:
        """Create a child span within this trace."""

    def set_output(self, output: Any) -> None:
        """Record the final output payload for the trace."""

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        """Attach metadata to the trace."""

    def __enter__(self) -> TraceContext:
        """Enter the trace context manager."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the trace context manager."""


@runtime_checkable
class Tracer(Protocol):
    """Protocol for creating top-level request traces."""

    def trace(
        self,
        name: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext:
        """Start a new trace."""

    def flush(self) -> None:
        """Flush buffered telemetry events if supported."""


class NoOpSpan:
    """No-operation span used when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def set_output(self, output: Any) -> None:
        return None

    def record_usage(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        return None

    def record_error(self, error: BaseException | str) -> None:
        return None

    def __enter__(self) -> NoOpSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


class NoOpTrace:
    """No-operation trace used when tracing is disabled."""

    def span(
        self,
        name: str,
        *,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> NoOpSpan:
        return NoOpSpan()

    def set_output(self, output: Any) -> None:
        return None

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        return None

    def __enter__(self) -> NoOpTrace:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


class NoOpTracer:
    """Default no-operation tracer."""

    def trace(
        self,
        name: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> NoOpTrace:
        return NoOpTrace()

    def flush(self) -> None:
        return None


@runtime_checkable
class MetricsRecorder(Protocol):
    """Domain-neutral port for recording low-cardinality operational metrics."""

    def record_http_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record one completed HTTP request."""

    def record_chat_turn(
        self,
        *,
        transport: str,
        mode: str,
        route_type: str,
        outcome: str,
    ) -> None:
        """Record one logical chat turn outcome."""

    def record_chat_ttft(self, *, duration_seconds: float) -> None:
        """Record SSE time-to-first-token (first content delta) in seconds."""

    def record_stage_duration(self, *, stage: str, duration_seconds: float) -> None:
        """Record execution duration of one bounded RAG/agent stage in seconds."""

    def record_llm_tokens(self, *, direction: str, count: int) -> None:
        """Record prompt/input or completion/output LLM token counts."""


class NoOpMetricsRecorder:
    """Default no-operation metrics recorder."""

    def record_http_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        return None

    def record_chat_turn(
        self,
        *,
        transport: str,
        mode: str,
        route_type: str,
        outcome: str,
    ) -> None:
        return None

    def record_chat_ttft(self, *, duration_seconds: float) -> None:
        return None

    def record_stage_duration(self, *, stage: str, duration_seconds: float) -> None:
        return None

    def record_llm_tokens(self, *, direction: str, count: int) -> None:
        return None


_active_metrics_recorder: MetricsRecorder = NoOpMetricsRecorder()


def get_metrics_recorder() -> MetricsRecorder:
    """Return active MetricsRecorder (never None)."""
    return _active_metrics_recorder


def set_metrics_recorder(recorder: MetricsRecorder) -> None:
    """Install active MetricsRecorder (called by Composition Root or tests)."""
    global _active_metrics_recorder  # noqa: PLW0603
    _active_metrics_recorder = recorder
