"""Concrete observability adapters (Langfuse v2 SDK + safe redaction & fallback)."""

from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Any

from app.shared.config import Settings, get_settings
from app.shared.observability import (
    NoOpSpan,
    NoOpTrace,
    NoOpTracer,
    SpanContext,
    TraceContext,
    Tracer,
    redact_secrets,
)

logger = logging.getLogger(__name__)

_SENSITIVE_TEXT_KEYS: frozenset[str] = frozenset(
    {
        "question",
        "q",
        "query",
        "retrieval_query",
        "corrected_query",
        "answer",
        "prompt",
        "content",
        "text",
        "sql",
    }
)
_SENSITIVE_LIST_KEYS: frozenset[str] = frozenset(
    {"queries", "tried", "chunks", "documents", "messages"}
)
_MAX_CONTENT_CHARS = 1000


def _sanitize_trace_payload(payload: Any, *, trace_content_enabled: bool) -> Any:
    """Sanitize trace/span payloads: mask secrets always; strip raw prompts/answers when disabled."""
    if payload is None or isinstance(payload, (bool, int, float)):
        return payload

    if isinstance(payload, str):
        cleaned = redact_secrets(payload)
        if not trace_content_enabled:
            return {"char_length": len(payload)}
        return cleaned[:_MAX_CONTENT_CHARS]

    if isinstance(payload, (list, tuple)):
        if not trace_content_enabled:
            return {"item_count": len(payload)}
        return [_sanitize_trace_payload(item, trace_content_enabled=True) for item in payload[:20]]

    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for key, value in payload.items():
            key_str = str(key)
            key_lower = key_str.lower()
            if not trace_content_enabled:
                if key_lower in _SENSITIVE_TEXT_KEYS and isinstance(value, str):
                    result[f"{key_str}_chars"] = len(value)
                    continue
                if key_lower in _SENSITIVE_LIST_KEYS and isinstance(value, (list, tuple)):
                    singular = "query" if key_lower == "queries" else key_str.rstrip("s")
                    result[f"{singular}_count"] = len(value)
                    continue
            if isinstance(value, str):
                cleaned_val = redact_secrets(value)
                result[key_str] = cleaned_val[:_MAX_CONTENT_CHARS] if trace_content_enabled else cleaned_val[:200]
            elif isinstance(value, (dict, list, tuple)):
                result[key_str] = _sanitize_trace_payload(
                    value, trace_content_enabled=trace_content_enabled
                )
            else:
                result[key_str] = value
        return result

    return redact_secrets(str(payload))[:200]


class LangfuseSpan:
    """Span wrapper forwarding lifecycle and sanitized metadata updates to a Langfuse v2 span."""

    def __init__(self, sdk_span: Any, *, trace_content_enabled: bool = False) -> None:
        self._sdk_span = sdk_span
        self._trace_content_enabled = trace_content_enabled
        self._metadata: dict[str, Any] = {}
        self._output: Any = None
        self._usage: dict[str, int] | None = None
        self._error: str | None = None
        self._started_at = time.perf_counter()

    def set_attribute(self, key: str, value: Any) -> None:
        self._metadata[key] = _sanitize_trace_payload(
            value, trace_content_enabled=self._trace_content_enabled
        )

    def set_output(self, output: Any) -> None:
        self._output = _sanitize_trace_payload(
            output, trace_content_enabled=self._trace_content_enabled
        )

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
        self._error = redact_secrets(str(error))[:300]

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
            logger.debug("Langfuse span end ignored due to error: %s", type(exc).__name__)


class LangfuseTrace:
    """Trace wrapper creating child Langfuse spans safely."""

    def __init__(self, sdk_trace: Any, *, trace_content_enabled: bool = False) -> None:
        self._sdk_trace = sdk_trace
        self._trace_content_enabled = trace_content_enabled
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
                sanitized_input = _sanitize_trace_payload(
                    input, trace_content_enabled=self._trace_content_enabled
                )
                sanitized_meta = _sanitize_trace_payload(
                    metadata or {}, trace_content_enabled=self._trace_content_enabled
                )
                sdk_span = self._sdk_trace.span(
                    name=name,
                    input=sanitized_input,
                    metadata=sanitized_meta,
                )
                return LangfuseSpan(sdk_span, trace_content_enabled=self._trace_content_enabled)
        except Exception as exc:
            logger.debug("Langfuse span creation failed for %s: %s", name, type(exc).__name__)
        return NoOpSpan()

    def set_output(self, output: Any) -> None:
        self._output = _sanitize_trace_payload(
            output, trace_content_enabled=self._trace_content_enabled
        )

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        sanitized = _sanitize_trace_payload(
            metadata, trace_content_enabled=self._trace_content_enabled
        )
        if isinstance(sanitized, dict):
            self._metadata.update(sanitized)

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
            logger.debug("Langfuse trace update ignored due to error: %s", type(exc).__name__)


class LangfuseTracer:
    """Tracer implementation backed by the Langfuse v2 Python SDK (`langfuse>=2.50.0,<3.0.0`)."""

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        host: str = "https://cloud.langfuse.com",
        client: Any = None,
        trace_content_enabled: bool = False,
        httpx_client: Any = None,
    ) -> None:
        self._trace_content_enabled = trace_content_enabled
        if client is not None:
            self._client = client
        else:
            from langfuse import Langfuse

            init_kwargs: dict[str, Any] = {
                "public_key": public_key,
                "secret_key": secret_key,
                "host": host,
            }
            if httpx_client is not None:
                init_kwargs["httpx_client"] = httpx_client
            self._client = Langfuse(**init_kwargs)

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
            sanitized_input = _sanitize_trace_payload(
                input, trace_content_enabled=self._trace_content_enabled
            )
            sanitized_meta = _sanitize_trace_payload(
                metadata or {}, trace_content_enabled=self._trace_content_enabled
            )
            sdk_trace = self._client.trace(
                name=name,
                session_id=session_id,
                user_id=user_id,
                input=sanitized_input,
                metadata=sanitized_meta,
            )
            return LangfuseTrace(sdk_trace, trace_content_enabled=self._trace_content_enabled)
        except Exception as exc:
            logger.warning(
                "Langfuse trace creation failed (%s); falling back to NoOpTrace.",
                type(exc).__name__,
            )
            return NoOpTrace()

    def flush(self) -> None:
        try:
            if hasattr(self._client, "flush"):
                self._client.flush()
        except Exception as exc:
            logger.debug("Langfuse flush ignored due to error: %s", type(exc).__name__)


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
            trace_content_enabled=bool(getattr(cfg, "langfuse_trace_content_enabled", False)),
        )
    except ImportError:
        logger.warning("langfuse package is not installed; using NoOpTracer.")
        return NoOpTracer()
    except Exception as exc:
        logger.warning("Failed to initialize LangfuseTracer (%s); using NoOpTracer.", type(exc).__name__)
        return NoOpTracer()
