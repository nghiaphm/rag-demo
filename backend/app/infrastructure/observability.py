"""Concrete observability adapters (Langfuse + safe fallback)."""

from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Any

from app.shared.config import Settings, get_settings
from app.shared.observability import NoOpSpan, NoOpTrace, NoOpTracer, SpanContext, TraceContext, Tracer

logger = logging.getLogger(__name__)


class LangfuseSpan:
    """Span wrapper forwarding lifecycle and metadata updates to a Langfuse span."""

    def __init__(self, sdk_span: Any) -> None:
        self._sdk_span = sdk_span
        self._metadata: dict[str, Any] = {}
        self._output: Any = None
        self._usage: dict[str, int] | None = None
        self._error: str | None = None
        self._started_at = time.perf_counter()

    def set_attribute(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def set_output(self, output: Any) -> None:
        self._output = output

    def record_usage(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        self._usage = {
            "input": prompt_tokens,
            "output": completion_tokens,
            "total": total_tokens,
        }

    def record_error(self, error: BaseException | str) -> None:
        self._error = str(error)

    def __enter__(self) -> LangfuseSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_val is not None:
            self.record_error(exc_val)
        elapsed_ms = round((time.perf_counter() - self._started_at) * 1000, 2)
        self._metadata.setdefault("latency_ms", elapsed_ms)

        try:
            end_kwargs: dict[str, Any] = {}
            if self._output is not None:
                end_kwargs["output"] = self._output
            if self._metadata:
                end_kwargs["metadata"] = self._metadata
            if self._usage is not None:
                end_kwargs["usage"] = self._usage
            if self._error is not None:
                end_kwargs["level"] = "ERROR"
                end_kwargs["status_message"] = self._error
            if hasattr(self._sdk_span, "end"):
                self._sdk_span.end(**end_kwargs)
        except Exception as exc:
            logger.debug("Langfuse span end ignored due to error: %s", exc)


class LangfuseTrace:
    """Trace wrapper creating child Langfuse spans safely."""

    def __init__(self, sdk_trace: Any) -> None:
        self._sdk_trace = sdk_trace
        self._metadata: dict[str, Any] = {}
        self._output: Any = None

    def span(
        self,
        name: str,
        *,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanContext:
        try:
            if hasattr(self._sdk_trace, "span"):
                sdk_span = self._sdk_trace.span(
                    name=name,
                    input=input,
                    metadata=metadata or {},
                )
                return LangfuseSpan(sdk_span)
        except Exception as exc:
            logger.debug("Langfuse span creation failed for %s: %s", name, exc)
        return NoOpSpan()

    def set_output(self, output: Any) -> None:
        self._output = output

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        self._metadata.update(metadata)

    def __enter__(self) -> LangfuseTrace:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            update_kwargs: dict[str, Any] = {}
            if self._output is not None:
                update_kwargs["output"] = self._output
            if self._metadata:
                update_kwargs["metadata"] = self._metadata
            if update_kwargs and hasattr(self._sdk_trace, "update"):
                self._sdk_trace.update(**update_kwargs)
        except Exception as exc:
            logger.debug("Langfuse trace update ignored due to error: %s", exc)


class LangfuseTracer:
    """Tracer implementation backed by the Langfuse Python SDK."""

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        host: str = "https://cloud.langfuse.com",
        client: Any = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )

    def trace(
        self,
        name: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext:
        try:
            sdk_trace = self._client.trace(
                name=name,
                session_id=session_id,
                user_id=user_id,
                input=input,
                metadata=metadata or {},
            )
            return LangfuseTrace(sdk_trace)
        except Exception as exc:
            logger.warning("Langfuse trace creation failed; falling back to NoOpTrace: %s", exc)
            return NoOpTrace()

    def flush(self) -> None:
        try:
            if hasattr(self._client, "flush"):
                self._client.flush()
        except Exception as exc:
            logger.debug("Langfuse flush ignored due to error: %s", exc)


def get_tracer(settings: Settings | None = None) -> Tracer:
    """Create the configured tracer, falling back to NoOpTracer when disabled or unconfigured."""
    cfg = settings or get_settings()
    if not cfg.langfuse_enabled:
        return NoOpTracer()

    public_key = cfg.langfuse_public_key.get_secret_value() if cfg.langfuse_public_key else None
    secret_key = cfg.langfuse_secret_key.get_secret_value() if cfg.langfuse_secret_key else None
    if not public_key or not secret_key:
        logger.warning("LANGFUSE_ENABLED is true but Langfuse keys are missing; using NoOpTracer.")
        return NoOpTracer()

    try:
        return LangfuseTracer(
            public_key=public_key,
            secret_key=secret_key,
            host=cfg.langfuse_host,
        )
    except ImportError:
        logger.warning("langfuse package is not installed; using NoOpTracer.")
        return NoOpTracer()
    except Exception as exc:
        logger.warning("Failed to initialize LangfuseTracer (%s); using NoOpTracer.", exc)
        return NoOpTracer()
