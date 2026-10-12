"""Deterministic P5-05 history evaluation helper tests."""

import unittest

from evaluation.history_eval import build_history_turns, summarize
from scripts.eval_history_cli import _acceptance


class HistoryEvaluationTests(unittest.TestCase):
    def test_long_session_builder_keeps_padding_before_relevant_turn(self):
        case = {
            "padding_turns": 3,
            "history": [{"user": "Embedding nào?", "assistant": "gemini-embedding-001"}],
        }
        turns = build_history_turns(case)
        self.assertEqual(len(turns), 4)
        self.assertEqual(turns[-1].user.content, "Embedding nào?")
        self.assertEqual(turns[-1].assistant.content, "gemini-embedding-001")
        self.assertEqual(
            [turn.user.sequence for turn in turns],
            [1, 3, 5, 7],
        )
        self.assertEqual(len({turn.user.request_id for turn in turns}), 4)

    def test_summary_reports_paired_deltas_referent_and_budget(self):
        cases = [
            {
                "category": "pronoun_follow_up",
                "baseline": self._run(hit=False, recall=0.0, relevant=False, latency=100, tokens=10),
                "history_aware": self._run(hit=True, recall=1.0, relevant=True, latency=130, tokens=15),
            },
            {
                "category": "out_of_document",
                "baseline": self._run(
                    hit=None, recall=None, relevant=None, latency=90, tokens=8, fallback=True
                ),
                "history_aware": self._run(
                    hit=None, recall=None, relevant=None, latency=95, tokens=8, fallback=True
                ),
            },
        ]
        summary = summarize(cases)
        self.assertEqual(summary["baseline"]["retrieval_hit_rate"], 0.0)
        self.assertEqual(summary["history_aware"]["retrieval_hit_rate"], 1.0)
        self.assertEqual(summary["delta"]["retrieval_hit_rate"], 1.0)
        self.assertEqual(summary["referent_accuracy"], 1.0)
        self.assertTrue(summary["all_budgets_ok"])
        self.assertEqual(summary["delta"]["total_tokens"], 5.0)

    def test_acceptance_allows_grounding_guard_fallback_after_provider_call(self):
        case = {"expect_fallback": False, "expect_rewrite": True}
        run = {
            "error": None,
            "retrieval_hit": True,
            "answer_fact_coverage": 1.0,
            "rewrite_provider_calls": 1,
            "rewrite_reason": "context_reference",
            "rewritten": False,
            "omitted_history_turns": 0,
            "budget_ok": True,
        }
        acceptance = _acceptance(case, run, retrieval_only=False)
        self.assertTrue(acceptance["rewrite_ok"])
        self.assertTrue(acceptance["passed"])

    def test_acceptance_rejects_rewrite_call_for_independent_query(self):
        case = {"expect_fallback": False, "expect_rewrite": False}
        run = {
            "error": None,
            "retrieval_hit": True,
            "answer_fact_coverage": 1.0,
            "rewrite_provider_calls": 1,
            "rewrite_reason": None,
            "rewritten": False,
            "omitted_history_turns": 0,
            "budget_ok": True,
        }
        acceptance = _acceptance(case, run, retrieval_only=False)
        self.assertFalse(acceptance["rewrite_ok"])
        self.assertFalse(acceptance["passed"])

    def test_retrieval_only_summary_does_not_claim_referent_answer_accuracy(self):
        run = self._run(
            hit=True,
            recall=1.0,
            relevant=None,
            latency=None,
            tokens=10,
        )
        summary = summarize(
            [
                {
                    "category": "pronoun_follow_up",
                    "baseline": run,
                    "history_aware": run,
                }
            ]
        )
        self.assertIsNone(summary["referent_accuracy"])

    @staticmethod
    def _run(
        *,
        hit,
        recall,
        relevant,
        latency,
        tokens,
        fallback=None,
    ):
        return {
            "error": None,
            "retrieval_hit": hit,
            "retrieval_recall": recall,
            "answer_fact_coverage": 1.0 if relevant else (0.0 if relevant is False else None),
            "answer_relevant": relevant,
            "faithful": True,
            "fallback_correct": fallback,
            "budget_ok": True,
            "latency_ms": {"total": latency},
            "tokens": {"total": tokens},
        }


if __name__ == "__main__":
    unittest.main()
