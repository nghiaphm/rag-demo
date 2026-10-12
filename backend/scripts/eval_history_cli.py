"""P5-05 paired baseline/history-aware evaluation on isolated Qdrant data."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.cloud_connections import QdrantConnection
from app.config import settings
from app.qdrant_ingestion import QdrantVectorIndex
from app.rag.embeddings import get_embeddings
from app.rag.pipeline import (
    generate_prepared_answer,
    prepare_rag_request_from_components,
)
from app.rag.retriever import get_retriever
from evaluation.history_eval import build_history_turns, score_run, summarize
from scripts.eval_cli import (
    EVAL_COLLECTION,
    _active_eval_versions,
    _index_corpus,
)

EVAL_DIR = BACKEND_DIR / "evaluation"
GOLDEN_SET_PATH = EVAL_DIR / "history_golden_set.json"
RESULTS_DIR = EVAL_DIR / "results"
MAX_ATTEMPTS = 3


async def _run_mode(
    case: dict[str, Any],
    *,
    history_turns: tuple,
    active_version_ids: tuple[str, ...],
    retriever: Any,
    retrieval_only: bool,
) -> dict[str, Any]:
    """Run one mode with bounded retry; never expose raw provider details."""
    last_error: Exception | None = None
    prepare_latency_ms: float | None = None
    generation_latency_ms: float | None = None
    for attempt in range(MAX_ATTEMPTS):
        prepared = None
        try:
            started = time.perf_counter()
            prepared = await prepare_rag_request_from_components(
                case["question"],
                history_turns=history_turns,
                active_version_ids=active_version_ids,
                retriever=retriever,
            )
            prepare_latency_ms = (time.perf_counter() - started) * 1000
            generated = None
            if not retrieval_only:
                started = time.perf_counter()
                generated = await generate_prepared_answer(prepared)
                generation_latency_ms = (time.perf_counter() - started) * 1000
            return score_run(
                case,
                prepared=prepared,
                generated=generated,
                prepare_latency_ms=prepare_latency_ms,
                generation_latency_ms=generation_latency_ms,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001 - provider/network may be transient
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(2 * (attempt + 1))
    return score_run(
        case,
        prepared=None,
        generated=None,
        prepare_latency_ms=prepare_latency_ms,
        generation_latency_ms=generation_latency_ms,
        error=None if last_error is None else type(last_error).__name__,
    )


def _acceptance(case: dict[str, Any], run: dict[str, Any], retrieval_only: bool) -> dict[str, Any]:
    retrieval_ok = (
        True if case.get("expect_fallback") else run.get("retrieval_hit") is True
    )
    answer_ok = True
    if not retrieval_only:
        answer_ok = (
            run.get("fallback_correct") is True
            if case.get("expect_fallback")
            else run.get("answer_fact_coverage") == 1.0
        )
    # Dependent queries must exercise the provider, but a lexical-grounding
    # rejection remains a valid safe fallback. Independent queries must make
    # no rewrite call. Retrieval/answer checks below decide whether the
    # fallback still resolved the referent correctly.
    rewrite_ok = (
        run.get("rewrite_provider_calls") == 1
        and run.get("rewrite_reason") == "context_reference"
        if case.get("expect_rewrite")
        else run.get("rewrite_provider_calls") == 0
        and run.get("rewritten") is False
    )
    history_budget_ok = (
        (run.get("omitted_history_turns") or 0) > 0
        if case.get("expect_history_omitted")
        else True
    )
    return {
        "retrieval_ok": retrieval_ok,
        "answer_ok": answer_ok,
        "rewrite_ok": rewrite_ok,
        "history_budget_ok": history_budget_ok,
        "passed": bool(
            not run.get("error")
            and retrieval_ok
            and answer_ok
            and rewrite_ok
            and history_budget_ok
            and run.get("budget_ok")
        ),
    }


async def _evaluate(*, no_reindex: bool, retrieval_only: bool) -> dict[str, Any]:
    connection = QdrantConnection()
    status = connection.connect()
    if not status.ok or connection.client is None:
        print(f"BLOCKED: qdrant ok={status.ok}; code={status.code}")
        raise SystemExit(2)
    embeddings = get_embeddings()
    vector_index = QdrantVectorIndex(connection.client, EVAL_COLLECTION)
    try:
        indexed = [] if no_reindex else _index_corpus(vector_index, embeddings)
        active_versions = _active_eval_versions()
        retriever = get_retriever(
            vector_index=vector_index,
            embeddings=embeddings,
            active_version_ids=active_versions,
        )
        golden = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
        cases: list[dict[str, Any]] = []
        for case in golden["cases"]:
            history_turns = build_history_turns(case)
            baseline = await _run_mode(
                case,
                history_turns=(),
                active_version_ids=active_versions,
                retriever=retriever,
                retrieval_only=retrieval_only,
            )
            history_aware = await _run_mode(
                case,
                history_turns=history_turns,
                active_version_ids=active_versions,
                retriever=retriever,
                retrieval_only=retrieval_only,
            )
            result = {
                "id": case["id"],
                "category": case["category"],
                "question": case["question"],
                "expected_sources": case.get("expected_sources", []),
                "expected_facts": case.get("expected_facts", []),
                "expect_fallback": bool(case.get("expect_fallback")),
                "baseline": baseline,
                "history_aware": history_aware,
                "acceptance": _acceptance(case, history_aware, retrieval_only),
            }
            cases.append(result)
            print(
                f"[{case['id']}] pass={result['acceptance']['passed']} "
                f"baseline_hit={baseline.get('retrieval_hit')} "
                f"history_hit={history_aware.get('retrieval_hit')} "
                f"rewrite={history_aware.get('rewrite_status')} "
                f"error={history_aware.get('error')}"
            )
        report = {
            "golden_set": golden["name"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "retrieval_only" if retrieval_only else "live_generation",
            "config": {
                "llm_model": settings.llm_model,
                "embedding_model": settings.embedding_model,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "top_k": settings.top_k,
                "collection": EVAL_COLLECTION,
                "indexed": indexed,
            },
            "cases": cases,
            "summary": summarize(cases),
        }
        report["summary"]["acceptance_pass_rate"] = round(
            sum(case["acceptance"]["passed"] for case in cases) / len(cases), 3
        )
        return report
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="P5-05 paired history-aware evaluation")
    parser.add_argument("--no-reindex", action="store_true")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Bỏ qua final generation khi provider quota không khả dụng.",
    )
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "p5_history_eval.json")
    args = parser.parse_args()
    report = asyncio.run(
        _evaluate(no_reindex=args.no_reindex, retrieval_only=args.retrieval_only)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n===== P5-05 SUMMARY =====")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    print(f"Đã lưu kết quả: {args.out}")


if __name__ == "__main__":
    main()
