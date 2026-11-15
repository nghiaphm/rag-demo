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

        tracer = LangfuseTracer(public_key="pk", secret_key="sk", client=sdk_client)
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


if __name__ == "__main__":
    unittest.main()
