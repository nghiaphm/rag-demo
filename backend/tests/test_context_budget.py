"""P5-02 tests for bounded, whole-turn context selection and truncation."""

import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.config import Settings
from app.context_budget import (
    ApproximateTokenCounter,
    ContextBudgetBuilder,
    ContextBudgetConfig,
    ContextBudgetError,
)
from app.conversation_models import MessageRecord, MessageRole, MessageStatus
from app.history import HistoryTurn


def _turn(sequence: int, *, text: str = "short") -> HistoryTurn:
    session_id = str(uuid4())
    request_id = str(uuid4())
    return HistoryTurn(
        user=MessageRecord(
            session_id=session_id,
            sequence=sequence,
            role=MessageRole.USER,
            content=f"user-{text}",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        ),
        assistant=MessageRecord(
            session_id=session_id,
            sequence=sequence + 1,
            role=MessageRole.ASSISTANT,
            content=f"assistant-{text}",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        ),
    )


def _config(**overrides) -> ContextBudgetConfig:
    values = {
        "context_window_tokens": 1000,
        "system_max_tokens": 100,
        "history_max_tokens": 300,
        "chunks_max_tokens": 300,
        "query_max_tokens": 100,
        "output_reserve_tokens": 100,
        "chars_per_token": 1.0,
    }
    values.update(overrides)
    return ContextBudgetConfig(**values)


class ContextBudgetTests(unittest.TestCase):
    def test_environment_settings_reject_allocations_over_context_window(self):
        with self.assertRaises(ValidationError):
            Settings(
                groq_api_key="test",
                embedding_api_key="test",
                rag_context_window_tokens=100,
                _env_file=None,
            )

    def test_environment_settings_validate_rewrite_limits(self):
        for values in (
            {"rag_rewrite_timeout_seconds": 0},
            {"rag_rewrite_max_chars": 0},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                Settings(
                    groq_api_key="test",
                    embedding_api_key="test",
                    _env_file=None,
                    **values,
                )

    def test_allocations_must_fit_context_window(self):
        with self.assertRaises(ValueError):
            _config(context_window_tokens=899)
        with self.assertRaises(ValueError):
            _config(query_max_tokens=0)

    def test_usage_covers_every_component_and_never_exceeds_allocations(self):
        builder = ContextBudgetBuilder(_config())
        result = builder.build(
            system="system instruction",
            history_turns=[_turn(1), _turn(3)],
            chunks=["[1] source\nfirst chunk", "[2] source\nsecond chunk"],
            query="current question",
        )

        self.assertLessEqual(result.usage.system, builder.config.system_max_tokens)
        self.assertLessEqual(result.usage.history, builder.config.history_max_tokens)
        self.assertLessEqual(result.usage.chunks, builder.config.chunks_max_tokens)
        self.assertLessEqual(result.usage.query, builder.config.query_max_tokens)
        self.assertEqual(
            result.usage.output_reserve, builder.config.output_reserve_tokens
        )
        self.assertLessEqual(result.usage.total, builder.config.context_window_tokens)

    def test_selects_only_most_recent_whole_turns_in_chronological_order(self):
        turns = [_turn(1), _turn(3), _turn(5)]
        counter = ApproximateTokenCounter(chars_per_token=1.0)
        per_turn = counter.turn(turns[0])
        builder = ContextBudgetBuilder(
            _config(history_max_tokens=per_turn * 2, context_window_tokens=1000)
        )

        result = builder.build(
            system="system", history_turns=turns, chunks=[], query="question"
        )

        self.assertEqual([turn.user.sequence for turn in result.history_turns], [3, 5])
        self.assertEqual(result.omitted_history_turns, 1)

    def test_oversized_newest_turn_does_not_fall_back_to_older_turn(self):
        older = _turn(1, text="tiny")
        newest = _turn(3, text="x" * 200)
        counter = ApproximateTokenCounter(chars_per_token=1.0)
        history_limit = counter.turn(older)
        builder = ContextBudgetBuilder(
            _config(history_max_tokens=history_limit, context_window_tokens=1000)
        )

        result = builder.build(
            system="system",
            history_turns=[older, newest],
            chunks=[],
            query="question",
        )

        self.assertEqual(result.history_turns, ())
        self.assertEqual(result.omitted_history_turns, 2)

    def test_query_uses_deterministic_head_tail_truncation(self):
        query = "BEGIN-" + ("middle" * 30) + "-END"
        builder = ContextBudgetBuilder(_config(query_max_tokens=40))

        result = builder.build(
            system="system", history_turns=[], chunks=[], query=query
        )

        self.assertTrue(result.query_truncated)
        self.assertIn("[truncated]", result.query)
        self.assertTrue(result.query.startswith("BEGIN"))
        self.assertTrue(result.query.endswith("END"))
        self.assertLessEqual(result.usage.query, 40)

    def test_chunks_keep_rank_and_only_last_selected_chunk_is_truncated(self):
        chunks = ["rank-one", "rank-two-" + ("x" * 100), "rank-three"]
        counter = ApproximateTokenCounter(chars_per_token=1.0)
        first_cost = counter.human(chunks[0])
        builder = ContextBudgetBuilder(
            _config(chunks_max_tokens=first_cost + 35)
        )

        result = builder.build(
            system="system", history_turns=[], chunks=chunks, query="question"
        )

        self.assertEqual(result.chunks[0], "rank-one")
        self.assertEqual(len(result.chunks), 2)
        self.assertIn("[truncated]", result.chunks[1])
        self.assertTrue(result.chunks_truncated)
        self.assertEqual(result.omitted_chunks, 1)
        self.assertLessEqual(result.usage.chunks, builder.config.chunks_max_tokens)

    def test_system_instruction_is_rejected_instead_of_truncated(self):
        builder = ContextBudgetBuilder(_config(system_max_tokens=10))
        with self.assertRaises(ContextBudgetError):
            builder.build(
                system="safety " * 20,
                history_turns=[],
                chunks=[],
                query="question",
            )

    def test_tiny_query_allocation_fails_instead_of_returning_empty_query(self):
        builder = ContextBudgetBuilder(_config(query_max_tokens=1))
        with self.assertRaises(ContextBudgetError):
            builder.build(
                system="system",
                history_turns=[],
                chunks=[],
                query="a long question",
            )


if __name__ == "__main__":
    unittest.main()
