"""RAGAS-aligned evaluation metrics with offline deterministic and LLM-judge support.

Computes the four core RAGAS dimensions:
- Context Precision: fraction of retrieved contexts that are relevant to expected sources/facts.
- Context Recall: fraction of expected ground-truth facts/sources covered by retrieved contexts.
- Faithfulness: fraction of answer sentences grounded in the retrieved contexts.
- Answer Relevancy: alignment between the generated answer and the user question / ground truth.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from evaluation.scoring.metrics import _content_tokens, fact_present


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class RagasSample:
    """Single evaluated RAG turn for RAGAS + latency/cost aggregation."""

    question: str
    answer: str
    contexts: tuple[str, ...]
    expected_facts: tuple[str, ...] = ()
    expected_sources: tuple[str, ...] = ()
    retrieved_sources: tuple[str, ...] = ()
    ground_truth: str = ""
    latency_ms: float = 0.0
    ttft_ms: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class RagasScore:
    """Normalized [0.0, 1.0] scores for a single RAGAS sample."""

    context_precision: float
    context_recall: float
    faithfulness: float
    answer_relevancy: float

    @property
    def overall_score(self) -> float:
        return round(
            (
                self.context_precision
                + self.context_recall
                + self.faithfulness
                + self.answer_relevancy
            )
            / 4.0,
            4,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "context_precision": round(self.context_precision, 4),
            "context_recall": round(self.context_recall, 4),
            "faithfulness": round(self.faithfulness, 4),
            "answer_relevancy": round(self.answer_relevancy, 4),
            "overall_score": self.overall_score,
        }


def _jaccard_overlap(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union else 0.0


def _split_claims(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text or "") if part.strip()]


def score_context_precision(sample: RagasSample) -> float:
    """Precision@K style relevance of retrieved contexts/sources."""
    if not sample.contexts and not sample.retrieved_sources:
        return 1.0 if not sample.expected_sources and not sample.expected_facts else 0.0

    if sample.expected_sources and sample.retrieved_sources:
        expected_set = {s.lower() for s in sample.expected_sources}
        hits = 0
        precision_sum = 0.0
        for idx, src in enumerate(sample.retrieved_sources, start=1):
            if src.lower() in expected_set:
                hits += 1
                precision_sum += hits / idx
        return round(precision_sum / len(sample.expected_sources), 4) if hits else 0.0

    if not sample.contexts:
        return 0.0

    ref_tokens = _content_tokens(sample.question)
    for fact in sample.expected_facts:
        ref_tokens |= _content_tokens(fact)
    if not ref_tokens:
        return 1.0

    relevant = sum(
        1
        for ctx in sample.contexts
        if len(_content_tokens(ctx) & ref_tokens) >= max(1, min(2, len(ref_tokens)))
    )
    return round(relevant / len(sample.contexts), 4)


def score_context_recall(sample: RagasSample) -> float:
    """Fraction of expected facts / sources covered by retrieved contexts."""
    if sample.expected_facts:
        joined_ctx = "\n".join(sample.contexts)
        covered = sum(1 for fact in sample.expected_facts if fact_present(fact, joined_ctx))
        return round(covered / len(sample.expected_facts), 4)

    if sample.expected_sources:
        retrieved_set = {s.lower() for s in sample.retrieved_sources}
        covered = sum(1 for src in sample.expected_sources if src.lower() in retrieved_set)
        return round(covered / len(sample.expected_sources), 4)

    return 1.0 if sample.contexts else 0.0


def score_faithfulness(sample: RagasSample) -> float:
    """Fraction of answer claims/sentences supported by retrieved contexts."""
    claims = _split_claims(sample.answer)
    if not claims:
        return 0.0
    if not sample.contexts:
        # Refusal/fallback answers with no context are considered faithful only if no factual claims.
        return 0.0

    ctx_tokens = _content_tokens(" ".join(sample.contexts))
    if not ctx_tokens:
        return 0.0

    supported = 0
    for claim in claims:
        claim_tokens = _content_tokens(claim)
        if not claim_tokens:
            supported += 1
            continue
        overlap_ratio = len(claim_tokens & ctx_tokens) / len(claim_tokens)
        if overlap_ratio >= 0.45:
            supported += 1
    return round(supported / len(claims), 4)


def score_answer_relevancy(sample: RagasSample) -> float:
    """Measures how directly the answer addresses the question and ground truth."""
    ans_tokens = _content_tokens(sample.answer)
    if not ans_tokens:
        return 0.0

    q_tokens = _content_tokens(sample.question)
    q_coverage = (len(ans_tokens & q_tokens) / len(q_tokens)) if q_tokens else 0.0

    if sample.expected_facts:
        fact_cov = sum(
            1 for fact in sample.expected_facts if fact_present(fact, sample.answer)
        ) / len(sample.expected_facts)
        return round(min(1.0, 0.35 * q_coverage + 0.65 * fact_cov), 4)

    if sample.ground_truth:
        gt_tokens = _content_tokens(sample.ground_truth)
        return round(min(1.0, 0.4 * q_coverage + 0.6 * _jaccard_overlap(ans_tokens, gt_tokens)), 4)

    return round(min(1.0, q_coverage), 4)


def evaluate_ragas_sample(
    sample: RagasSample,
    *,
    llm_judge: Callable[[RagasSample], dict[str, float]] | None = None,
) -> RagasScore:
    """Score a single sample using deterministic metrics or an optional LLM judge."""
    if llm_judge is not None:
        judged = llm_judge(sample)
        return RagasScore(
            context_precision=float(judged.get("context_precision", score_context_precision(sample))),
            context_recall=float(judged.get("context_recall", score_context_recall(sample))),
            faithfulness=float(judged.get("faithfulness", score_faithfulness(sample))),
            answer_relevancy=float(judged.get("answer_relevancy", score_answer_relevancy(sample))),
        )

    return RagasScore(
        context_precision=score_context_precision(sample),
        context_recall=score_context_recall(sample),
        faithfulness=score_faithfulness(sample),
        answer_relevancy=score_answer_relevancy(sample),
    )


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(float(sorted_values[0]), 2)
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(float(sorted_values[lower]), 2)
    weight = rank - lower
    interpolated = sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight
    return round(float(interpolated), 2)


def compute_latency_percentiles(
    latencies_ms: Sequence[float],
    ttft_ms_values: Sequence[float] = (),
) -> dict[str, float]:
    """Compute p50/p95/mean latency and optional TTFT percentiles in milliseconds."""
    sorted_lat = sorted(float(v) for v in latencies_ms)
    result: dict[str, float] = {
        "p50_ms": _percentile(sorted_lat, 50),
        "p95_ms": _percentile(sorted_lat, 95),
        "mean_ms": round(sum(sorted_lat) / len(sorted_lat), 2) if sorted_lat else 0.0,
    }
    if ttft_ms_values:
        sorted_ttft = sorted(float(v) for v in ttft_ms_values)
        result["ttft_p50_ms"] = _percentile(sorted_ttft, 50)
        result["ttft_p95_ms"] = _percentile(sorted_ttft, 95)
    return result


def aggregate_ragas_scores(scores: Sequence[RagasScore]) -> dict[str, float]:
    """Average RAGAS scores across a collection of evaluated samples."""
    if not scores:
        return {
            "context_precision": 0.0,
            "context_recall": 0.0,
            "faithfulness": 0.0,
            "answer_relevancy": 0.0,
            "overall_score": 0.0,
        }
    n = len(scores)
    return {
        "context_precision": round(sum(s.context_precision for s in scores) / n, 4),
        "context_recall": round(sum(s.context_recall for s in scores) / n, 4),
        "faithfulness": round(sum(s.faithfulness for s in scores) / n, 4),
        "answer_relevancy": round(sum(s.answer_relevancy for s in scores) / n, 4),
        "overall_score": round(sum(s.overall_score for s in scores) / n, 4),
    }
