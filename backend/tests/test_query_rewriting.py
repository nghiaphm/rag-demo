"""P5-03 tests for conditional, grounded query rewriting and metrics."""

import asyncio
from types import SimpleNamespace
import unittest
from uuid import uuid4

from app.conversation_models import MessageRecord, MessageRole, MessageStatus
from app.history import HistoryTurn
from app.query_rewriting import (
    ProviderRewrite,
    QueryRewriter,
    RewriteStatus,
    _message_text,
    _usage_from_message,
)


def _turn() -> HistoryTurn:
    session_id = str(uuid4())
    request_id = str(uuid4())
    return HistoryTurn(
        user=MessageRecord(
            session_id=session_id,
            sequence=1,
            role=MessageRole.USER,
            content="Cho tôi thông tin sản phẩm Alpha",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        ),
        assistant=MessageRecord(
            session_id=session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            content="Sản phẩm Alpha có bảo hành hai năm",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        ),
    )


class FakeProvider:
    def __init__(
        self,
        response: ProviderRewrite | None = None,
        *,
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.response = response
        self.error = error
        self.delay = delay
        self.prompts: list[str] = []

    async def rewrite(self, prompt: str) -> ProviderRewrite:
        self.prompts.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("missing fake response")
        return self.response


class QueryRewriterTests(unittest.IsolatedAsyncioTestCase):
    def test_langchain_message_text_blocks_are_normalized(self):
        message = SimpleNamespace(
            content=[{"type": "text", "text": "Alpha "}, "warranty"]
        )
        self.assertEqual(_message_text(message), "Alpha warranty")

    def test_langchain_provider_usage_shapes_are_normalized(self):
        self.assertEqual(
            _usage_from_message(
                SimpleNamespace(
                    usage_metadata={
                        "input_tokens": 12,
                        "output_tokens": 3,
                        "total_tokens": 15,
                    },
                    response_metadata={},
                )
            ),
            {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
        )
        self.assertEqual(
            _usage_from_message(
                SimpleNamespace(
                    usage_metadata=None,
                    response_metadata={
                        "usage": {"prompt_tokens": 7, "completion_tokens": 2}
                    },
                )
            ),
            {"input_tokens": 7, "output_tokens": 2, "total_tokens": 9},
        )

    async def test_no_history_never_calls_provider(self):
        provider = FakeProvider(ProviderRewrite("unused"))
        result = await QueryRewriter(
            provider, timeout_seconds=1, max_chars=200
        ).rewrite("Còn nó?", [])

        self.assertEqual(result.status, RewriteStatus.SKIPPED_NO_HISTORY)
        self.assertEqual(result.retrieval_query, result.original_query)
        self.assertEqual(result.metrics.provider_calls, 0)
        self.assertEqual(provider.prompts, [])

    async def test_independent_query_never_calls_provider(self):
        provider = FakeProvider(ProviderRewrite("unused"))
        original = "Giá sản phẩm Alpha là bao nhiêu?"
        result = await QueryRewriter(
            provider, timeout_seconds=1, max_chars=200
        ).rewrite(original, [_turn()])

        self.assertEqual(result.status, RewriteStatus.SKIPPED_INDEPENDENT)
        self.assertEqual(result.retrieval_query, original)
        self.assertEqual(result.metrics.total_tokens, 0)
        self.assertEqual(provider.prompts, [])

    async def test_dependent_query_is_rewritten_and_original_is_preserved(self):
        provider = FakeProvider(
            ProviderRewrite(
                "Bảo hành của sản phẩm Alpha?",
                usage={"input_tokens": 30, "output_tokens": 8, "total_tokens": 38},
            )
        )
        clock = iter([10.0, 10.025]).__next__
        original = "Còn bảo hành của nó?"
        result = await QueryRewriter(
            provider, timeout_seconds=1, max_chars=200, clock=clock
        ).rewrite(original, [_turn()])

        self.assertEqual(result.status, RewriteStatus.REWRITTEN)
        self.assertTrue(result.rewritten)
        self.assertEqual(result.original_query, original)
        self.assertEqual(result.retrieval_query, "Bảo hành của sản phẩm Alpha?")
        self.assertEqual(result.metrics.provider_calls, 1)
        self.assertEqual(result.metrics.latency_ms, 25.0)
        self.assertEqual(result.metrics.total_tokens, 38)
        self.assertEqual(result.metrics.usage_source, "provider")
        self.assertIn("ORIGINAL_QUERY", provider.prompts[0])

    async def test_new_entity_or_fact_is_rejected_as_ungrounded(self):
        for candidate in ("Bảo hành của Beta?", "Alpha bảo hành 5 năm?"):
            with self.subTest(candidate=candidate):
                provider = FakeProvider(ProviderRewrite(candidate))
                result = await QueryRewriter(
                    provider, timeout_seconds=1, max_chars=200
                ).rewrite("Còn bảo hành của nó?", [_turn()])
                self.assertEqual(result.status, RewriteStatus.REJECTED_UNGROUNDED)
                self.assertFalse(result.rewritten)
                self.assertEqual(result.retrieval_query, result.original_query)
                self.assertEqual(result.metrics.usage_source, "estimated")

    async def test_multiline_same_or_oversized_output_is_rejected(self):
        candidates = (
            "Còn bảo hành của nó?",
            "Bảo hành Alpha?\nGiải thích",
            "Alpha " * 100,
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate[:20]):
                result = await QueryRewriter(
                    FakeProvider(ProviderRewrite(candidate)),
                    timeout_seconds=1,
                    max_chars=40,
                ).rewrite("Còn bảo hành của nó?", [_turn()])
                self.assertEqual(result.status, RewriteStatus.REJECTED_INVALID)
                self.assertEqual(result.retrieval_query, result.original_query)

    async def test_provider_error_and_timeout_fall_back_without_raw_detail(self):
        error_result = await QueryRewriter(
            FakeProvider(error=RuntimeError("private provider response")),
            timeout_seconds=1,
            max_chars=200,
        ).rewrite("Còn nó?", [_turn()])
        timeout_result = await QueryRewriter(
            FakeProvider(ProviderRewrite("unused"), delay=0.02),
            timeout_seconds=0.001,
            max_chars=200,
        ).rewrite("Còn nó?", [_turn()])

        self.assertEqual(error_result.status, RewriteStatus.PROVIDER_ERROR)
        self.assertEqual(timeout_result.status, RewriteStatus.PROVIDER_TIMEOUT)
        self.assertEqual(error_result.retrieval_query, "Còn nó?")
        self.assertEqual(timeout_result.retrieval_query, "Còn nó?")
        self.assertEqual(error_result.metrics.provider_calls, 1)
        self.assertEqual(timeout_result.metrics.provider_calls, 1)


if __name__ == "__main__":
    unittest.main()
