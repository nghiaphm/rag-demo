"""Unit tests for Phase 1 RAGAS metrics and baseline evaluation helpers."""

from __future__ import annotations

import unittest

from evaluation.scoring.ragas_metrics import (
    RagasSample,
    aggregate_ragas_scores,
    compute_latency_percentiles,
    evaluate_ragas_sample,
)


class TestRagasMetrics(unittest.TestCase):
    def test_evaluate_ragas_sample_deterministic_high_quality(self) -> None:
        sample = RagasSample(
            question="Vector của gemini-embedding-001 có bao nhiêu chiều?",
            answer="Vector của gemini-embedding-001 có 3072 chiều.",
            contexts=("Model gemini-embedding-001 tạo vector 3072 chiều.",),
            expected_facts=("3072",),
            expected_sources=("llm-embedding.md",),
            retrieved_sources=("llm-embedding.md",),
            latency_ms=42.0,
            ttft_ms=12.0,
        )
        score = evaluate_ragas_sample(sample)
        self.assertEqual(score.context_precision, 1.0)
        self.assertEqual(score.context_recall, 1.0)
        self.assertEqual(score.faithfulness, 1.0)
        self.assertGreater(score.answer_relevancy, 0.8)
        self.assertGreater(score.overall_score, 0.9)

    def test_evaluate_ragas_sample_uses_llm_judge_hook_when_provided(self) -> None:
        sample = RagasSample(
            question="Q?",
            answer="A.",
            contexts=("ctx",),
        )
        score = evaluate_ragas_sample(
            sample,
            llm_judge=lambda _s: {
                "context_precision": 0.9,
                "context_recall": 0.8,
                "faithfulness": 1.0,
                "answer_relevancy": 0.7,
            },
        )
        self.assertEqual(score.context_precision, 0.9)
        self.assertEqual(score.context_recall, 0.8)
        self.assertEqual(score.faithfulness, 1.0)
        self.assertEqual(score.answer_relevancy, 0.7)
        self.assertEqual(score.overall_score, 0.85)

    def test_aggregate_and_latency_percentiles(self) -> None:
        s1 = evaluate_ragas_sample(
            RagasSample(
                question="What is Qdrant?",
                answer="Qdrant is a vector database.",
                contexts=("Qdrant is a vector database for embeddings.",),
                expected_facts=("vector database",),
            )
        )
        s2 = evaluate_ragas_sample(
            RagasSample(
                question="Unknown topic?",
                answer="No info.",
                contexts=(),
                expected_facts=("missing",),
            )
        )
        agg = aggregate_ragas_scores([s1, s2])
        self.assertGreater(agg["overall_score"], 0.0)
        self.assertLess(agg["overall_score"], 1.0)

        lat = compute_latency_percentiles([10.0, 20.0, 30.0, 40.0, 100.0], [5.0, 10.0, 15.0])
        self.assertEqual(lat["p50_ms"], 30.0)
        self.assertEqual(lat["p95_ms"], 88.0)
        self.assertEqual(lat["ttft_p50_ms"], 10.0)


if __name__ == "__main__":
    unittest.main()
