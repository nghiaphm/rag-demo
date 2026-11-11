"""Safe request-level metrics for the SSE chat transport."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from collections.abc import Callable


logger = logging.getLogger("app.chat_stream.metrics")


@dataclass(frozen=True)
class StreamMetric:
    request_id: str
    mode: str
    outcome: str
    first_event_ms: float | None
    first_content_ms: float | None
    total_latency_ms: float
    delta_count: int


class StreamMetricTracker:
    """Monotonic one-shot tracker shared across pre-header and stream stages."""

    def __init__(
        self,
        *,
        started_at: float | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._clock = clock
        self._started_at = clock() if started_at is None else started_at
        self._first_event_at: float | None = None
        self._first_content_at: float | None = None
        self._delta_count = 0
        self._finished = False

    def mark_first_event(self) -> None:
        if self._first_event_at is None:
            self._first_event_at = self._clock()

    def mark_content(self) -> None:
        if self._first_content_at is None:
            self._first_content_at = self._clock()
        self._delta_count += 1

    def finish(self, *, request_id: str, mode: str, outcome: str) -> StreamMetric | None:
        if self._finished:
            return None
        self._finished = True
        finished_at = self._clock()

        def elapsed(timestamp: float | None) -> float | None:
            if timestamp is None:
                return None
            return round(max(0.0, timestamp - self._started_at) * 1000, 3)

        return StreamMetric(
            request_id=request_id,
            mode=mode,
            outcome=outcome,
            first_event_ms=elapsed(self._first_event_at),
            first_content_ms=elapsed(self._first_content_at),
            total_latency_ms=elapsed(finished_at) or 0.0,
            delta_count=self._delta_count,
        )


def record_stream_metric(metric: StreamMetric) -> None:
    """Write only bounded operational fields; never prompt, answer or secrets."""
    logger.info(
        "chat_stream_metrics request_id=%s mode=%s outcome=%s "
        "first_event_ms=%s first_content_ms=%s total_latency_ms=%s delta_count=%s",
        metric.request_id,
        metric.mode,
        metric.outcome,
        metric.first_event_ms,
        metric.first_content_ms,
        metric.total_latency_ms,
        metric.delta_count,
    )
