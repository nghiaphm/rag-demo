"""P4-05 deterministic tests for SSE latency metrics."""

import unittest

from app.api.streaming.stream_metrics import StreamMetric, StreamMetricTracker, record_stream_metric


class FakeClock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class StreamMetricTests(unittest.TestCase):
    def test_first_event_first_content_and_total_latency(self):
        tracker = StreamMetricTracker(started_at=10.0, clock=FakeClock([10.01, 10.04, 10.1]))
        tracker.mark_first_event()
        tracker.mark_content()
        tracker.mark_content()
        metric = tracker.finish(
            request_id="request-id", mode="PERSISTENT", outcome="COMPLETED"
        )
        self.assertEqual(metric.first_event_ms, 10.0)
        self.assertEqual(metric.first_content_ms, 40.0)
        self.assertEqual(metric.total_latency_ms, 100.0)
        self.assertEqual(metric.delta_count, 2)

    def test_no_content_is_nullable_and_finish_is_idempotent(self):
        tracker = StreamMetricTracker(started_at=5.0, clock=FakeClock([5.02, 5.07]))
        tracker.mark_first_event()
        metric = tracker.finish(
            request_id="request-id", mode="STATELESS", outcome="RAG_STREAM_EMPTY"
        )
        self.assertEqual(metric.first_event_ms, 20.0)
        self.assertIsNone(metric.first_content_ms)
        self.assertEqual(metric.delta_count, 0)
        self.assertIsNone(
            tracker.finish(
                request_id="request-id", mode="STATELESS", outcome="COMPLETED"
            )
        )

    def test_structured_log_contains_only_bounded_operational_fields(self):
        metric = StreamMetric(
            request_id="request-id",
            mode="PERSISTENT",
            outcome="RAG_STREAM_ERROR",
            first_event_ms=1.0,
            first_content_ms=2.0,
            total_latency_ms=3.0,
            delta_count=1,
        )
        with self.assertLogs("app.chat_stream.metrics", level="INFO") as captured:
            record_stream_metric(metric)
        line = captured.output[0]
        for expected in (
            "request_id=request-id",
            "mode=PERSISTENT",
            "outcome=RAG_STREAM_ERROR",
            "first_event_ms=1.0",
            "first_content_ms=2.0",
            "total_latency_ms=3.0",
            "delta_count=1",
        ):
            self.assertIn(expected, line)
        for forbidden in ("question=", "answer=", "sources=", "api_key=", "credentials="):
            self.assertNotIn(forbidden, line)

    def test_record_stream_metric_forwards_ttft_seconds_to_metrics_recorder(self):
        from app.shared.observability import NoOpMetricsRecorder, set_metrics_recorder

        observed_ttft: list[float] = []

        class _SpyMetrics(NoOpMetricsRecorder):
            def record_chat_ttft(self, *, duration_seconds: float) -> None:
                observed_ttft.append(duration_seconds)

        set_metrics_recorder(_SpyMetrics())
        try:
            metric = StreamMetric(
                request_id="req-1",
                mode="STATELESS",
                outcome="COMPLETED",
                first_event_ms=10.0,
                first_content_ms=250.0,
                total_latency_ms=600.0,
                delta_count=3,
            )
            record_stream_metric(metric)
        finally:
            set_metrics_recorder(NoOpMetricsRecorder())

        self.assertEqual(observed_ttft, [0.25])


if __name__ == "__main__":
    unittest.main()
