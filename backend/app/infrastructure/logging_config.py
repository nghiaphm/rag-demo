"""Structured JSON/text logging configuration with request_id injection and secret redaction."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any

from app.shared.config import Settings, get_settings
from app.shared.observability import get_request_id, redact_secrets


class RequestIdLogFilter(logging.Filter):
    """Injects `request_id` from contextvars onto every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id") or getattr(record, "request_id", None) is None:
            record.request_id = get_request_id()
        return True


class RedactingJsonFormatter(logging.Formatter):
    """Single-line JSON log formatter that masks credentials/tokens in messages and tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", None) or get_request_id()
        raw_message = record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(raw_message),
            "request_id": req_id,
        }
        if record.exc_info:
            formatted_exc = self.formatException(record.exc_info)
            payload["exception"] = redact_secrets(formatted_exc)
        elif record.exc_text:
            payload["exception"] = redact_secrets(str(record.exc_text))
        return json.dumps(payload, ensure_ascii=False)


class RedactingTextFormatter(logging.Formatter):
    """Human-readable single/multi-line text formatter with secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", None) or get_request_id() or "-"
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = f"{ts} {record.levelname} [{req_id}] {record.name}: {redact_secrets(record.getMessage())}"
        if record.exc_info:
            base = f"{base}\n{redact_secrets(self.formatException(record.exc_info))}"
        return base


def configure_logging(settings: Settings | None = None) -> None:
    """Configure application logging level, JSON/text formatter, and request_id filter."""
    cfg = settings or get_settings()
    level = getattr(logging, cfg.log_level.upper(), logging.INFO)
    formatter: logging.Formatter = (
        RedactingJsonFormatter()
        if cfg.log_format.lower() == "json"
        else RedactingTextFormatter()
    )
    req_filter = RequestIdLogFilter()

    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    app_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler.addFilter(req_filter)
    app_logger.addHandler(handler)
    app_logger.propagate = False
