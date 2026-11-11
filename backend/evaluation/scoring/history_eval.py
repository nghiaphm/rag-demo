"""Deterministic scoring helpers for paired P5-05 history-aware evaluation."""

from __future__ import annotations

import statistics
from typing import Any
from uuid import uuid4

from app.conversations.models import MessageRecord, MessageRole, MessageStatus
from app.shared.config import settings
from app.conversations.history import HistoryTurn
from evaluation.scoring.metrics import (
    answer_fact_coverage,
    faithfulness_ratio,
    retrieval_metrics,
)

FALLBACK_PHRASE = "Không tìm thấy thông tin trong tài liệu"
FAITHFULNESS_THRESHOLD = 0.7


def build_history_turns(case: dict[str, Any]) -> tuple[HistoryTurn, ...]:
    """Create stable whole turns, with optional old padding for long-session cases."""
    session_id = str(uuid4())
    values: list[tuple[str, str]] = []
    for index in range(int(case.get("padding_turns", 0))):
        values.append(
            (
                f"Lượt cũ {index}: mô tả vận hành không liên quan " + "x" * 160,
                f"Phản hồi cũ {index}: dữ liệu đệm lịch sử " + "y" * 160,
            )
        )
    values.extend((item["user"], item["assistant"]) for item in case.get("history", []))

    turns: list[HistoryTurn] = []
    for index, (user_content, assistant_content) in enumerate(values):
        request_id = str(uuid4())
        sequence = index * 2 + 1
        turns.append(
            HistoryTurn(
                user=MessageRecord(
                    session_id=session_id,
                    sequence=sequence,
                    role=MessageRole.USER,
                    content=user_content,
                    status=MessageStatus.COMPLETED,
                    request_id=request_id,
                ),
                assistant=MessageRecord(
                    session_id=session_id,
                    sequence=sequence + 1,
                    role=MessageRole.ASSISTANT,
                    content=assistant_content,
                    status=MessageStatus.COMPLETED,
                    request_id=request_id,
                ),
            )
        )
    return tuple(turns)


def score_run(
    case: dict[str, Any],
    *,
    prepared: Any | None,
    generated: dict[str, Any] | None,
    prepare_latency_ms: float | None,
    generation_latency_ms: float | None,
    error: str | None,
) -> dict[str, Any]:
    """Score one baseline or history-aware execution without an LLM judge."""
    if prepared is None:
        return {
            "error": error,
            "retrieval_hit": None,
            "retrieval_recall": None,
            "answer_fact_coverage": None,
            "answer_relevant": None,
            "faithfulness_ratio": None,
            "faithful": False,
            "fallback_correct": None,
            "budget_ok": False,
            "rewrite_status": None,
            "rewritten": False,
            "rewrite_provider_calls": 0,
            "omitted_history_turns": None,
            "latency_ms": {"prepare": prepare_latency_ms, "generation": generation_latency_ms, "total": None},
            "tokens": _empty_tokens(),
        }

    sources = [source.get("file_name") for source in prepared.sources]
    retrieval = retrieval_metrics(sources, case.get("expected_sources", []))
    answer = "" if generated is None else str(generated.get("answer", ""))
    context = "\n\n".join(prepared.budget.chunks)
    expect_fallback = bool(case.get("expect_fallback"))
    coverage = None if expect_fallback or not answer else answer_fact_coverage(
        answer, case.get("expected_facts", [])
    )
    faith_ratio = None if not answer else faithfulness_ratio(answer, context)
    fallback_correct = None
    if expect_fallback and answer:
        fallback_correct = FALLBACK_PHRASE in answer
    total_latency = None
    if prepare_latency_ms is not None and generation_latency_ms is not None:
        total_latency = round(prepare_latency_ms + generation_latency_ms, 1)
    generation_usage = None if generated is None else generated.get("usage")
    rewrite_metrics = prepared.rewrite.metrics
    return {
        "error": error,
        "retrieved_sources": sorted({source for source in sources if source}),
        "retrieval_hit": retrieval["retrieval_hit"],
        "retrieval_recall": retrieval["retrieval_recall"],
        "answer": answer,
        "answer_fact_coverage": coverage,
        "answer_relevant": None if coverage is None else coverage >= 1.0,
        "faithfulness_ratio": None if faith_ratio is None else round(faith_ratio, 3),
        "faithful": (
            None
            if not answer
            else (
                bool(fallback_correct)
                if expect_fallback
                else faith_ratio is not None and faith_ratio >= FAITHFULNESS_THRESHOLD
            )
        ),
        "fallback_correct": fallback_correct,
        "budget_ok": prepared.budget.usage.total <= settings.rag_context_window_tokens,
        "budget_usage": prepared.budget.usage.__dict__,
        "rewrite_status": prepared.rewrite.status.value,
        "rewritten": prepared.rewrite.rewritten,
        "rewrite_provider_calls": rewrite_metrics.provider_calls,
        "rewrite_reason": prepared.rewrite.dependency_reason,
        "omitted_history_turns": prepared.budget.omitted_history_turns,
        "latency_ms": {
            "prepare": None if prepare_latency_ms is None else round(prepare_latency_ms, 1),
            "generation": None if generation_latency_ms is None else round(generation_latency_ms, 1),
            "total": total_latency,
        },
        "tokens": _merge_tokens(rewrite_metrics, generation_usage),
    }


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate paired modes and explicit history-minus-baseline deltas."""
    baseline = _mode_summary([case["baseline"] for case in cases])
    history = _mode_summary([case["history_aware"] for case in cases])
    referent_cases = [
        case for case in cases if case["category"] in {"pronoun_follow_up", "long_session", "cross_document"}
    ]
    referent_correct = [
        bool(case["history_aware"].get("retrieval_hit"))
        and case["history_aware"].get("answer_fact_coverage") == 1.0
        for case in referent_cases
        if not case["history_aware"].get("error")
        and case["history_aware"].get("answer_fact_coverage") is not None
    ]
    return {
        "n_cases": len(cases),
        "baseline": baseline,
        "history_aware": history,
        "delta": {
            key: _delta(history.get(key), baseline.get(key))
            for key in (
                "retrieval_hit_rate",
                "mean_retrieval_recall",
                "answer_relevance_rate",
                "faithfulness_rate",
                "fallback_accuracy",
                "mean_total_latency_ms",
                "total_tokens",
            )
        },
        "referent_accuracy": _mean(referent_correct),
        "all_budgets_ok": all(
            case["history_aware"].get("budget_ok", False)
            for case in cases
            if not case["history_aware"].get("error")
        ),
    }


def _mode_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [run for run in runs if not run.get("error")]
    in_doc = [run for run in ok if run.get("answer_fact_coverage") is not None]
    fallback = [run for run in ok if run.get("fallback_correct") is not None]
    return {
        "n_ok": len(ok),
        "n_errors": len(runs) - len(ok),
        "retrieval_hit_rate": _mean(
            [bool(run["retrieval_hit"]) for run in ok if run.get("retrieval_hit") is not None]
        ),
        "mean_retrieval_recall": _mean(
            [run["retrieval_recall"] for run in ok if run.get("retrieval_recall") is not None]
        ),
        "answer_relevance_rate": _mean([bool(run["answer_relevant"]) for run in in_doc]),
        "faithfulness_rate": _mean(
            [bool(run["faithful"]) for run in ok if run.get("faithful") is not None]
        ),
        "fallback_accuracy": _mean([bool(run["fallback_correct"]) for run in fallback]),
        "mean_total_latency_ms": _mean(
            [run["latency_ms"]["total"] for run in ok if run["latency_ms"]["total"] is not None]
        ),
        "total_tokens": sum(run["tokens"]["total"] for run in ok),
    }


def _merge_tokens(rewrite: Any, generation: dict[str, int] | None) -> dict[str, Any]:
    generation = generation or {}
    generation_total = int(generation.get("total_tokens", 0))
    return {
        "rewrite": rewrite.total_tokens,
        "generation": generation_total,
        "total": rewrite.total_tokens + generation_total,
        "generation_available": bool(generation),
        "rewrite_usage_source": rewrite.usage_source,
    }


def _empty_tokens() -> dict[str, Any]:
    return {
        "rewrite": 0,
        "generation": 0,
        "total": 0,
        "generation_available": False,
        "rewrite_usage_source": "none",
    }


def _mean(values: list[Any]) -> float | None:
    if not values:
        return None
    return round(statistics.fmean(values), 3)


def _delta(current: Any, baseline: Any) -> float | None:
    if current is None or baseline is None:
        return None
    return round(float(current) - float(baseline), 3)
