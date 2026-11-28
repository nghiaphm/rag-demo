"""Agent & Excel SQL Trajectory Evaluation Metrics (T3.3).

Measures agentic orchestration, tool selection, SQL AST guard compliance,
numerical ground-truth accuracy, citation validity, step count, latency, and tokens.

TRANSPARENCY & RUN-MODE SEPARATION:
- `run_mode="offline_smoke"` uses a deterministic scripted model strictly to validate
  technical plumbing (`ChatOrchestrator`, `AgenticRunner`, `ToolExecutor`, `sql_guard`,
  `DuckDBSqlExecutor`). Reports in this mode set `valid_for_model_quality=False` and
  carry the banner `"OFFLINE_PLUMBING_CHECK — NOT VALID FOR MODEL QUALITY CLAIMS"`.
- `run_mode="live_eval"` is the ONLY mode valid for evaluating real LLM tool selection
  and DuckDB SQL authoring against an isolated evaluation collection (`rag_documents_eval`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from app.documents.excel.sql_guard import validate_and_rewrite_sql
from evaluation.scoring.metrics import answer_fact_coverage
from evaluation.scoring.ragas_metrics import compute_latency_percentiles


AgentRunMode = Literal["offline_smoke", "live_eval"]

OFFLINE_SMOKE_BANNER = "OFFLINE_PLUMBING_CHECK — NOT VALID FOR MODEL QUALITY CLAIMS"
LIVE_EVAL_BANNER = "LIVE_LLM_EVALUATION — ISOLATED EVAL COLLECTION"


@dataclass(frozen=True)
class AgentEvalCase:
    """Golden test case specification for Agentic / Excel SQL evaluation."""

    case_id: str
    question: str
    expected_route: str = "AGENTIC"
    expected_tools: tuple[str, ...] = ()
    expected_facts: tuple[str, ...] = ()
    expect_sql: bool = False
    ground_truth: str = ""


@dataclass(frozen=True)
class AgentTurnObservation:
    """Observed trajectory and telemetry from executing one agentic turn."""

    case_id: str
    actual_route: str
    called_tools: tuple[str, ...] = ()
    generated_sql: tuple[str, ...] = ()
    allowed_views: tuple[str, ...] = ()
    answer: str = ""
    citations_valid: bool = True
    agent_steps: int = 1
    latency_ms: float = 0.0
    ttft_ms: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class AgentTrajectoryReport:
    """Aggregated trajectory report with explicit offline vs. live provenance."""

    run_mode: AgentRunMode
    valid_for_model_quality: bool
    banner: str
    total_cases: int
    route_accuracy: float
    tool_selection_precision: float
    tool_selection_recall: float
    sql_guard_pass_rate: float
    sql_execution_accuracy: float
    citation_validity_rate: float
    avg_agent_steps: float
    p50_ms: float
    p95_ms: float
    ttft_p50_ms: float
    total_tokens: int
    case_results: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "route_accuracy": self.route_accuracy,
            "tool_selection_precision": self.tool_selection_precision,
            "tool_selection_recall": self.tool_selection_recall,
            "sql_guard_pass_rate": self.sql_guard_pass_rate,
            "sql_execution_accuracy": self.sql_execution_accuracy,
            "citation_validity_rate": self.citation_validity_rate,
            "avg_agent_steps": self.avg_agent_steps,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "ttft_p50_ms": self.ttft_p50_ms,
            "total_tokens": self.total_tokens,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_mode": self.run_mode,
            "valid_for_model_quality": self.valid_for_model_quality,
            "banner": self.banner,
            "summary": self.summary_dict(),
            "cases": list(self.case_results),
        }


def _score_tool_precision_recall(
    called_tools: Sequence[str],
    expected_tools: Sequence[str],
) -> tuple[float, float]:
    called_set = {t.strip() for t in called_tools if t and t.strip()}
    expected_set = {t.strip() for t in expected_tools if t and t.strip()}
    if not expected_set and not called_set:
        return 1.0, 1.0
    if not called_set:
        return 0.0, 0.0
    if not expected_set:
        return 0.0, 1.0
    hits = len(called_set & expected_set)
    return round(hits / len(called_set), 4), round(hits / len(expected_set), 4)


def _check_sql_guard(
    generated_sql: Sequence[str],
    allowed_views: Sequence[str],
    *,
    expect_sql: bool,
) -> tuple[bool | None, list[str]]:
    if not expect_sql and not generated_sql:
        return None, []
    if expect_sql and not generated_sql:
        return False, ["Expected run_sql query, but no SQL statement was generated."]

    reasons: list[str] = []
    all_ok = True
    for sql in generated_sql:
        guard_res = validate_and_rewrite_sql(sql, allowed_views=tuple(allowed_views))
        if not guard_res.ok:
            all_ok = False
            reasons.append(guard_res.reason or "SQL rejected by sql_guard.")
    return all_ok, reasons


def evaluate_agent_trajectory(
    cases: Sequence[AgentEvalCase],
    observations: Sequence[AgentTurnObservation],
    *,
    run_mode: AgentRunMode = "offline_smoke",
) -> AgentTrajectoryReport:
    """Evaluate agentic turn observations against golden expectations."""
    if run_mode not in ("offline_smoke", "live_eval"):
        raise ValueError(f"Invalid run_mode: {run_mode!r}")

    obs_by_id = {obs.case_id: obs for obs in observations}
    route_hits = 0
    precisions: list[float] = []
    recalls: list[float] = []
    sql_guard_outcomes: list[bool] = []
    sql_exec_outcomes: list[bool] = []
    citation_outcomes: list[bool] = []
    steps_list: list[int] = []
    latencies_ms: list[float] = []
    ttft_values_ms: list[float] = []
    total_tokens = 0
    case_results: list[dict[str, Any]] = []

    for case in cases:
        obs = obs_by_id.get(case.case_id)
        if obs is None:
            raise KeyError(f"Missing AgentTurnObservation for case_id={case.case_id!r}")

        route_ok = obs.actual_route == case.expected_route
        if route_ok:
            route_hits += 1

        prec, rec = _score_tool_precision_recall(obs.called_tools, case.expected_tools)
        precisions.append(prec)
        recalls.append(rec)

        sql_guard_ok, guard_reasons = _check_sql_guard(
            obs.generated_sql,
            obs.allowed_views,
            expect_sql=case.expect_sql,
        )
        fact_cov = answer_fact_coverage(obs.answer, list(case.expected_facts))

        if sql_guard_ok is not None:
            sql_guard_outcomes.append(sql_guard_ok)
        if case.expect_sql:
            sql_exec_ok = bool(sql_guard_ok) and fact_cov >= 1.0
            sql_exec_outcomes.append(sql_exec_ok)
        else:
            sql_exec_ok = None

        citation_outcomes.append(bool(obs.citations_valid))
        steps_list.append(int(obs.agent_steps))
        latencies_ms.append(float(obs.latency_ms))
        if obs.ttft_ms is not None:
            ttft_values_ms.append(float(obs.ttft_ms))
        turn_tokens = int(obs.prompt_tokens) + int(obs.completion_tokens)
        total_tokens += turn_tokens

        case_results.append(
            {
                "case_id": case.case_id,
                "question": case.question,
                "expected_route": case.expected_route,
                "actual_route": obs.actual_route,
                "route_ok": route_ok,
                "expected_tools": list(case.expected_tools),
                "called_tools": list(obs.called_tools),
                "tool_precision": prec,
                "tool_recall": rec,
                "sql_guard_ok": sql_guard_ok,
                "sql_guard_reasons": guard_reasons,
                "sql_execution_ok": sql_exec_ok,
                "fact_coverage": round(fact_cov, 4),
                "citations_valid": bool(obs.citations_valid),
                "agent_steps": int(obs.agent_steps),
                "latency_ms": round(float(obs.latency_ms), 3),
                "ttft_ms": round(float(obs.ttft_ms), 3) if obs.ttft_ms is not None else None,
                "tokens": turn_tokens,
            }
        )

    n = len(cases)
    lat_summary = compute_latency_percentiles(latencies_ms, ttft_values_ms)

    return AgentTrajectoryReport(
        run_mode=run_mode,
        valid_for_model_quality=(run_mode == "live_eval"),
        banner=LIVE_EVAL_BANNER if run_mode == "live_eval" else OFFLINE_SMOKE_BANNER,
        total_cases=n,
        route_accuracy=round(route_hits / n, 4) if n else 0.0,
        tool_selection_precision=round(sum(precisions) / n, 4) if n else 0.0,
        tool_selection_recall=round(sum(recalls) / n, 4) if n else 0.0,
        sql_guard_pass_rate=(
            round(sum(1 for ok in sql_guard_outcomes if ok) / len(sql_guard_outcomes), 4)
            if sql_guard_outcomes
            else 1.0
        ),
        sql_execution_accuracy=(
            round(sum(1 for ok in sql_exec_outcomes if ok) / len(sql_exec_outcomes), 4)
            if sql_exec_outcomes
            else 1.0
        ),
        citation_validity_rate=(
            round(sum(1 for ok in citation_outcomes if ok) / n, 4) if n else 0.0
        ),
        avg_agent_steps=round(sum(steps_list) / n, 4) if n else 0.0,
        p50_ms=lat_summary["p50_ms"],
        p95_ms=lat_summary["p95_ms"],
        ttft_p50_ms=lat_summary.get("ttft_p50_ms", 0.0),
        total_tokens=total_tokens,
        case_results=tuple(case_results),
    )
