"""Observability port definitions and no-op fallback implementations.

This module lives in ``app.shared`` so domain, RAG, and chat modules can
instrument execution spans without depending on concrete tracing SDKs.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol, runtime_checkable


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
