"""Unit tests for Observability ports and Langfuse/NoOp adapters."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.infrastructure.observability import LangfuseTracer, get_tracer
from app.shared.config import Settings
from app.shared.observability import NoOpTracer


class TestObservability(unittest.TestCase):
    def test_noop_tracer_lifecycle_is_safe(self) -> None:
        tracer = NoOpTracer()
        with tracer.trace("chat_turn", session_id="s-1", input={"q": "hi"}) as trace:
            with trace.span("retrieval", input={"queries": ["hi"]}) as span:
                span.set_attribute("k", 5)
                span.set_output({"count": 2})
                span.record_usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            trace.set_metadata({"env": "test"})
            trace.set_output({"answer": "hello"})
        tracer.flush()

    def test_get_tracer_returns_noop_when_disabled_or_missing_keys(self) -> None:
        disabled_cfg = Settings(langfuse_enabled=False)
        self.assertIsInstance(get_tracer(disabled_cfg), NoOpTracer)

        missing_keys_cfg = Settings(langfuse_enabled=True, langfuse_public_key=None, langfuse_secret_key=None)
        self.assertIsInstance(get_tracer(missing_keys_cfg), NoOpTracer)

    def test_langfuse_tracer_forwards_trace_and_span_lifecycle(self) -> None:
        sdk_span = MagicMock()
        sdk_trace = MagicMock()
        sdk_trace.span.return_value = sdk_span
        sdk_client = MagicMock()
        sdk_client.trace.return_value = sdk_trace

        tracer = LangfuseTracer(
            public_key="pk",
            secret_key="sk",
            client=sdk_client,
            trace_content_enabled=True,
        )
        with tracer.trace("rag_turn", session_id="sess-42", input={"q": "test"}) as trace:
            with trace.span("query_rewrite", input={"q": "test"}) as span:
                span.set_attribute("mode", "passthrough")
                span.record_usage(prompt_tokens=12, completion_tokens=8, total_tokens=20)
                span.set_output({"retrieval_query": "test"})
            trace.set_output({"answer_chars": 40})
        tracer.flush()

        sdk_client.trace.assert_called_once()
        sdk_trace.span.assert_called_once_with(
            name="query_rewrite",
            input={"q": "test"},
            metadata={},
        )
        sdk_span.end.assert_called_once()
        end_kwargs = sdk_span.end.call_args.kwargs
        self.assertEqual(end_kwargs["output"], {"retrieval_query": "test"})
        self.assertEqual(end_kwargs["usage"], {"input": 12, "output": 8, "total": 20})
        self.assertEqual(end_kwargs["metadata"]["mode"], "passthrough")
        self.assertIn("latency_ms", end_kwargs["metadata"])
        sdk_trace.update.assert_called_once()
        sdk_client.flush.assert_called_once()

    def test_langfuse_tracer_swallows_sdk_errors(self) -> None:
        broken_client = SimpleNamespace(
            trace=MagicMock(side_effect=RuntimeError("network down")),
            flush=MagicMock(side_effect=RuntimeError("flush down")),
        )
        tracer = LangfuseTracer(public_key="pk", secret_key="sk", client=broken_client)
        with tracer.trace("broken") as trace:
            with trace.span("step") as span:
                span.set_output({"ok": True})
        tracer.flush()

    def test_validate_or_generate_request_id_blocks_injection_and_overlong_headers(self) -> None:
        from uuid import UUID
        from app.shared.observability import validate_or_generate_request_id

        self.assertEqual(validate_or_generate_request_id("req-2026_11.27-ok"), "req-2026_11.27-ok")

        for malicious in (
            None,
            "",
            "   ",
            "bad\ninjected",
            "bad\r\nheader: evil",
            "bad space",
            "không-phải-ascii",
            "a" * 65,
            "semi;colon",
        ):
            generated = validate_or_generate_request_id(malicious)
            self.assertEqual(str(UUID(generated)), generated)

    def test_json_logging_includes_request_id_and_redacts_secrets_in_messages_and_exceptions(self) -> None:
        import json
        import logging
        from app.infrastructure.logging_config import RedactingJsonFormatter, RequestIdLogFilter
        from app.shared.observability import reset_request_id, set_request_id

        formatter = RedactingJsonFormatter()
        log_filter = RequestIdLogFilter()
        token = set_request_id("req-json-001")
        try:
            try:
                raise RuntimeError(
                    "Auth failed for mongodb+srv://admin:SuperSecret123@cluster0.mongodb.net/db "  # pragma: allowlist secret
                    "and key gsk_ABCDEFGHIJKLMNOPQRSTUVWX123456"  # pragma: allowlist secret
                )
            except RuntimeError:
                import sys

                record = logging.LogRecord(
                    name="app.test",
                    level=logging.ERROR,
                    pathname=__file__,
                    lineno=100,
                    msg="Upstream error with AIzaSyA1234567890abcdefghijklmnopqrstuv and Bearer eyJhbGciOiJIUzI1NiJ9.secret",  # pragma: allowlist secret
                    args=(),
                    exc_info=sys.exc_info(),
                )
            self.assertTrue(log_filter.filter(record))
            line = formatter.format(record)
        finally:
            reset_request_id(token)

        self.assertNotIn("\n", line)
        parsed = json.loads(line)
        self.assertEqual(parsed["request_id"], "req-json-001")
        self.assertEqual(parsed["level"], "ERROR")
        for leaked in (
            "SuperSecret123",
            "gsk_ABCDEFGHIJKLMNOPQRSTUVWX123456",  # pragma: allowlist secret
            "AIzaSyA1234567890abcdefghijklmnopqrstuv",  # pragma: allowlist secret
            "eyJhbGciOiJIUzI1NiJ9.secret",
        ):
            self.assertNotIn(leaked, line)
        self.assertIn("[REDACTED]", line)

    def test_langfuse_redacts_raw_prompts_and_answers_by_default(self) -> None:
        sdk_span = MagicMock()
        sdk_trace = MagicMock()
        sdk_trace.span.return_value = sdk_span
        sdk_client = MagicMock()
        sdk_client.trace.return_value = sdk_trace

        # Default trace_content_enabled=False
        tracer = LangfuseTracer(public_key="pk", secret_key="sk", client=sdk_client)
        secret_question = "Mức lương bí mật của Nguyễn Văn A là bao nhiêu?"
        secret_answer = "Mức lương là 50 triệu đồng và key gsk_ABCDEFGHIJKLMNOPQRSTUVWX"  # pragma: allowlist secret

        with tracer.trace(
            "rag_prepare",
            session_id="sess-1",
            input={"question": secret_question, "active_version_count": 2},
        ) as trace:
            with trace.span("query_rewrite", input={"question": secret_question}) as span:
                span.set_output({"retrieval_query": secret_question})
            trace.set_output({"answer": secret_answer, "source_count": 1})

        serialized_trace_call = repr(sdk_client.trace.call_args)
        serialized_span_call = repr(sdk_trace.span.call_args)
        serialized_end_call = repr(sdk_span.end.call_args)
        serialized_update_call = repr(sdk_trace.update.call_args)

        for call_repr in (
            serialized_trace_call,
            serialized_span_call,
            serialized_end_call,
            serialized_update_call,
        ):
            self.assertNotIn("Nguyễn Văn A", call_repr)
            self.assertNotIn("50 triệu đồng", call_repr)
            self.assertNotIn("gsk_ABCDEFGHIJKLMNOPQRSTUVWX", call_repr)  # pragma: allowlist secret

        # Quantitative safe metadata is preserved
        self.assertEqual(
            sdk_client.trace.call_args.kwargs["input"]["active_version_count"], 2
        )
        self.assertEqual(
            sdk_client.trace.call_args.kwargs["input"]["question_chars"], len(secret_question)
        )

    def test_langfuse_real_sdk_v2_offline_client_compatibility(self) -> None:
        import httpx

        def _mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok"})

        mock_http = httpx.Client(transport=httpx.MockTransport(_mock_handler))
        try:
            tracer = LangfuseTracer(
                public_key="pk-lf-offline-test",  # pragma: allowlist secret
                secret_key="sk-lf-offline-test",  # pragma: allowlist secret
                host="https://langfuse.invalid",
                httpx_client=mock_http,
            )
            with tracer.trace("sdk_compat_check", input={"question": "hello", "active_version_count": 1}) as trace:
                with trace.span("retrieval", input={"queries": ["hello"]}) as span:
                    span.set_attribute("raw_count", 3)
                    span.set_output({"selected_count": 2})
                trace.set_output({"source_count": 2})
            tracer.flush()
        finally:
            mock_http.close()

    def test_prometheus_metrics_exposition_and_low_cardinality_404_guard(self) -> None:
        from prometheus_client import CollectorRegistry
        from app.infrastructure.metrics import PrometheusMetricsRecorder

        registry = CollectorRegistry()
        recorder = PrometheusMetricsRecorder(registry=registry)
        for idx in range(50):
            recorder.record_http_request(
                method="GET",
                route="unmatched",
                status_code=404,
                duration_seconds=0.002,
            )
        recorder.record_http_request(
            method="GET",
            route="/documents/{document_id}",
            status_code=200,
            duration_seconds=0.015,
        )
        recorder.record_chat_turn(
            transport="sse",
            mode="persistent",
            route_type="rag",
            outcome="COMPLETED",
        )
        recorder.record_chat_ttft(duration_seconds=0.12)
        recorder.record_stage_duration(stage="retrieval", duration_seconds=0.04)
        recorder.record_llm_tokens(direction="input", count=120)
        recorder.record_llm_tokens(direction="output", count=45)

        payload = recorder.render().decode("utf-8")
        self.assertIn('rag_http_requests_total{method="GET",route="unmatched",status_code="404"} 50.0', payload)
        self.assertIn('rag_http_requests_total{method="GET",route="/documents/{document_id}",status_code="200"} 1.0', payload)
        self.assertIn('rag_chat_turns_total{mode="persistent",outcome="COMPLETED",route_type="rag",transport="sse"} 1.0', payload)
        self.assertIn('rag_stage_duration_seconds_count{stage="retrieval"} 1.0', payload)
        self.assertIn('rag_llm_tokens_total{direction="input"} 120.0', payload)
        self.assertIn('rag_llm_tokens_total{direction="output"} 45.0', payload)


if __name__ == "__main__":
    unittest.main()
