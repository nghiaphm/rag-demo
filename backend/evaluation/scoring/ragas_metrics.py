"""RAGAS-inspired custom evaluation metrics (deterministic heuristic & CustomLlmJudge).

TRANSPARENCY & METHODOLOGY NOTES:
1. These are **RAGAS-inspired custom metrics** implemented directly in this codebase
   (NOT the official `ragas` PyPI library). Function and class names (`RagasSample`,
   `RagasScore`, `evaluate_ragas_sample`, `aggregate_ragas_scores`) are preserved for
   backward compatibility with Phase 1 regression tests.
2. **In-scope vs. Out-of-scope separation (`expect_refusal`)**:
   - `context_precision`, `context_recall`, `faithfulness`, and `answer_relevancy` are
     averaged strictly over **in-scope** questions (`expect_refusal=False`).
   - **Out-of-scope** questions (`expect_refusal=True`) are evaluated separately via
     `correct_refusal` (`bool`) and aggregated into `correct_refusal_rate`, preventing
     legitimate empty-context refusals from distorting `faithfulness`.
3. **Strict non-mixing of scoring methods**:
   - Dataset reports explicitly declare `scoring_method`: `"deterministic_heuristic"`
     or `"custom_llm_judge"`.
   - When `scoring_method="custom_llm_judge"` fails on a sample, that sample is recorded
     with `scores=None` inside `judge_errors` (`judge_error_count`) and NEVER backfilled
     with deterministic heuristic numbers.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.documents import Document

from app.chat.corrective import EvidenceEvaluator
from evaluation.scoring.metrics import _content_tokens, fact_present


ScoringMethod = Literal["deterministic_heuristic", "custom_llm_judge"]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

_REFUSAL_MARKERS: tuple[str, ...] = (
    "không tìm thấy thông tin",
    "không tìm thấy dữ liệu",
    "không có thông tin",
    "không có dữ liệu",
    "không chứa thông tin",
    "tài liệu không đề cập",
    "không đề cập",
    "ngoài phạm vi",
    "chưa có thông tin",
    "không đủ thông tin",
    "thư viện không có",
    "kho tài liệu không chứa",
    "từ chối trả lời",
    "cannot find",
    "do not contain",
    "does not contain",
    "no supporting evidence",
    "no information",
    "not mentioned in the",
    "out of scope",
)


@dataclass(frozen=True)
class RagasSample:
    """Single evaluated RAG turn for RAGAS-inspired + latency/cost aggregation."""

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
    expect_refusal: bool = False


@dataclass(frozen=True)
class RagasScore:
    """Normalized [0.0, 1.0] scores for a single in-scope RAGAS-inspired sample."""

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


@dataclass(frozen=True)
class DatasetEvaluationReport:
    """Method-pure RAG evaluation report separating in-scope RAG metrics from refusal rate."""

    scoring_method: ScoringMethod
    metric_family: str
    total_samples: int
    in_scope_count: int
    valid_in_scope_count: int
    out_of_scope_count: int
    valid_out_of_scope_count: int
    correct_refusal_count: int
    correct_refusal_rate: float | None
    judge_error_count: int
    in_scope_summary: dict[str, float]
    groundedness_supplement: dict[str, float]
    latency_summary: dict[str, float]
    token_usage_summary: dict[str, int]
    sample_results: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    judge_errors: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scoring_method": self.scoring_method,
            "metric_family": self.metric_family,
            "total_samples": self.total_samples,
            "in_scope_count": self.in_scope_count,
            "valid_in_scope_count": self.valid_in_scope_count,
            "out_of_scope_count": self.out_of_scope_count,
            "valid_out_of_scope_count": self.valid_out_of_scope_count,
            "correct_refusal_count": self.correct_refusal_count,
            "correct_refusal_rate": self.correct_refusal_rate,
            "judge_error_count": self.judge_error_count,
            "in_scope_summary": dict(self.in_scope_summary),
            "groundedness_supplement": dict(self.groundedness_supplement),
            "latency_summary": dict(self.latency_summary),
            "token_usage_summary": dict(self.token_usage_summary),
            "sample_results": list(self.sample_results),
            "judge_errors": list(self.judge_errors),
        }


def _jaccard_overlap(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union else 0.0


def _split_claims(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text or "") if part.strip()]


def is_correct_refusal(answer: str, *, contexts: Sequence[str] = ()) -> bool:
    """Check whether an answer clearly declines an out-of-scope question."""
    normalized = " ".join((answer or "").lower().split())
    if not normalized:
        return False
    return any(marker in normalized for marker in _REFUSAL_MARKERS)


def evaluate_groundedness_supplement(sample: RagasSample) -> dict[str, Any]:
    """Run Corrective RAG's deterministic EvidenceEvaluator as an auxiliary groundedness signal."""
    evaluator = EvidenceEvaluator(llm=None)
    docs = [Document(page_content=ctx) for ctx in sample.contexts if ctx]
    result = evaluator._heuristic_evaluate(sample.answer, docs)
    return {
        "grounded": result.grounded,
        "support_ratio": result.support_ratio,
        "reason": result.reason,
    }


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
    """Score a single in-scope sample using deterministic metrics or an explicit judge hook."""
    if llm_judge is not None:
        judged = llm_judge(sample)
        return RagasScore(
            context_precision=float(judged["context_precision"]),
            context_recall=float(judged["context_recall"]),
            faithfulness=float(judged["faithfulness"]),
            answer_relevancy=float(judged["answer_relevancy"]),
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
    """Average RAGAS-inspired scores across a collection of valid in-scope samples."""
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


def evaluate_dataset_samples(
    samples: Sequence[RagasSample],
    *,
    scoring_method: ScoringMethod = "deterministic_heuristic",
    custom_judge: Any = None,
) -> DatasetEvaluationReport:
    """Evaluate a dataset cleanly: separate refusal rate from faithfulness and never mix judge methods."""
    if scoring_method not in ("deterministic_heuristic", "custom_llm_judge"):
        raise ValueError(f"Unsupported scoring_method: {scoring_method!r}")
    if scoring_method == "custom_llm_judge" and custom_judge is None:
        raise ValueError("custom_judge is required when scoring_method='custom_llm_judge'.")

    in_scope_count = 0
    out_of_scope_count = 0
    valid_in_scope_scores: list[RagasScore] = []
    valid_out_of_scope_count = 0
    correct_refusal_count = 0
    grounded_flags: list[bool] = []
    support_ratios: list[float] = []
    latencies_ms: list[float] = []
    ttft_values_ms: list[float] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    sample_results: list[dict[str, Any]] = []
    judge_errors: list[dict[str, Any]] = []

    for idx, sample in enumerate(samples):
        latencies_ms.append(float(sample.latency_ms))
        if sample.ttft_ms is not None:
            ttft_values_ms.append(float(sample.ttft_ms))
        total_prompt_tokens += int(sample.prompt_tokens)
        total_completion_tokens += int(sample.completion_tokens)

        if sample.expect_refusal:
            out_of_scope_count += 1
            if scoring_method == "deterministic_heuristic":
                refused = is_correct_refusal(sample.answer, contexts=sample.contexts)
                valid_out_of_scope_count += 1
                if refused:
                    correct_refusal_count += 1
                sample_results.append(
                    {
                        "index": idx,
                        "question": sample.question,
                        "expect_refusal": True,
                        "scores": None,
                        "correct_refusal": refused,
                        "judge_error": None,
                    }
                )
            else:
                try:
                    refused = bool(custom_judge.score_refusal(sample))
                    valid_out_of_scope_count += 1
                    if refused:
                        correct_refusal_count += 1
                    sample_results.append(
                        {
                            "index": idx,
                            "question": sample.question,
                            "expect_refusal": True,
                            "scores": None,
                            "correct_refusal": refused,
                            "judge_error": None,
                        }
                    )
                except Exception as exc:
                    err_msg = str(exc)
                    judge_errors.append(
                        {
                            "index": idx,
                            "question": sample.question,
                            "expect_refusal": True,
                            "error": err_msg,
                        }
                    )
                    sample_results.append(
                        {
                            "index": idx,
                            "question": sample.question,
                            "expect_refusal": True,
                            "scores": None,
                            "correct_refusal": None,
                            "judge_error": err_msg,
                        }
                    )
            continue

        # In-scope sample (`expect_refusal == False`)
        in_scope_count += 1
        supplement = evaluate_groundedness_supplement(sample)
        grounded_flags.append(bool(supplement["grounded"]))
        support_ratios.append(float(supplement["support_ratio"]))

        if scoring_method == "deterministic_heuristic":
            score = evaluate_ragas_sample(sample)
            valid_in_scope_scores.append(score)
            sample_results.append(
                {
                    "index": idx,
                    "question": sample.question,
                    "expect_refusal": False,
                    "scores": score.to_dict(),
                    "groundedness_supplement": supplement,
                    "correct_refusal": None,
                    "judge_error": None,
                }
            )
        else:
            try:
                score = custom_judge.score_sample(sample)
                valid_in_scope_scores.append(score)
                sample_results.append(
                    {
                        "index": idx,
                        "question": sample.question,
                        "expect_refusal": False,
                        "scores": score.to_dict(),
                        "groundedness_supplement": supplement,
                        "correct_refusal": None,
                        "judge_error": None,
                    }
                )
            except Exception as exc:
                err_msg = str(exc)
                judge_errors.append(
                    {
                        "index": idx,
                        "question": sample.question,
                        "expect_refusal": False,
                        "error": err_msg,
                    }
                )
                # CRITICAL: Never backfill deterministic heuristic scores when CustomLlmJudge fails!
                sample_results.append(
                    {
                        "index": idx,
                        "question": sample.question,
                        "expect_refusal": False,
                        "scores": None,
                        "groundedness_supplement": supplement,
                        "correct_refusal": None,
                        "judge_error": err_msg,
                    }
                )

    refusal_rate = (
        round(correct_refusal_count / valid_out_of_scope_count, 4)
        if valid_out_of_scope_count > 0
        else None
    )
    groundedness_summary = {
        "grounded_rate": (
            round(sum(1 for g in grounded_flags if g) / len(grounded_flags), 4)
            if grounded_flags
            else 0.0
        ),
        "mean_support_ratio": (
            round(sum(support_ratios) / len(support_ratios), 4)
            if support_ratios
            else 0.0
        ),
    }

    return DatasetEvaluationReport(
        scoring_method=scoring_method,
        metric_family="ragas_inspired_custom_metrics",
        total_samples=len(samples),
        in_scope_count=in_scope_count,
        valid_in_scope_count=len(valid_in_scope_scores),
        out_of_scope_count=out_of_scope_count,
        valid_out_of_scope_count=valid_out_of_scope_count,
        correct_refusal_count=correct_refusal_count,
        correct_refusal_rate=refusal_rate,
        judge_error_count=len(judge_errors),
        in_scope_summary=aggregate_ragas_scores(valid_in_scope_scores),
        groundedness_supplement=groundedness_summary,
        latency_summary=compute_latency_percentiles(latencies_ms, ttft_values_ms),
        token_usage_summary={
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
        },
        sample_results=tuple(sample_results),
        judge_errors=tuple(judge_errors),
    )
