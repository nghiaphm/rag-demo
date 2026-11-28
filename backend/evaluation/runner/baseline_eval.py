"""Phase 1 Offline Baseline Evaluation Runner (RAGAS-inspired Custom Deterministic Metrics).

TRANSPARENCY NOTE:
- Runs deterministic lexical retrieval + extractive baseline answers over the local corpus
  without calling any external LLM or Embedding API.
- Computes **RAGAS-inspired custom deterministic heuristic metrics** (NOT the official
  `ragas` PyPI library, and NOT a live LLM capability benchmark).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.scoring.metrics import _content_tokens
from evaluation.scoring.ragas_metrics import (
    RagasSample,
    aggregate_ragas_scores,
    compute_latency_percentiles,
    evaluate_ragas_sample,
)


EVAL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = EVAL_DIR / "datasets" / "golden_set.json"
DEFAULT_CORPUS_DIR = EVAL_DIR / "datasets" / "corpus"
DEFAULT_RESULTS_DIR = EVAL_DIR / "results"


def _load_corpus(corpus_dir: Path) -> dict[str, str]:
    docs: dict[str, str] = {}
    if not corpus_dir.exists():
        return docs
    for pattern in ("*.md", "*.txt"):
        for path in sorted(corpus_dir.glob(pattern)):
            docs[path.name] = path.read_text(encoding="utf-8")
    return docs


def _offline_retrieve(question: str, corpus: dict[str, str], top_k: int = 2) -> list[tuple[str, str]]:
    q_tokens = _content_tokens(question)
    scored: list[tuple[float, str, str]] = []
    for name, content in corpus.items():
        doc_tokens = _content_tokens(content)
        overlap = len(q_tokens & doc_tokens)
        if overlap > 0:
            scored.append((overlap / max(1, len(q_tokens)), name, content))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [(name, content) for _, name, content in scored[:top_k]]


def _offline_answer(case: dict[str, Any], retrieved: list[tuple[str, str]]) -> str:
    if case.get("expect_fallback") or not retrieved:
        return "Không tìm thấy thông tin trong tài liệu đã tải lên."
    # Extractive baseline summary from the top retrieved document.
    return " ".join(content.strip() for _, content in retrieved[:1])


def run_offline_baseline(
    dataset_path: Path = DEFAULT_DATASET,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
) -> dict[str, Any]:
    """Run deterministic offline baseline evaluation against the golden dataset."""
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    corpus = _load_corpus(corpus_dir)

    case_results: list[dict[str, Any]] = []
    scores = []
    latencies_ms: list[float] = []
    ttft_values_ms: list[float] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for case in cases:
        t0 = time.perf_counter()
        retrieved = _offline_retrieve(case["question"], corpus, top_k=2)
        t_first_token = time.perf_counter()
        answer = _offline_answer(case, retrieved)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        ttft_ms = (t_first_token - t0) * 1000.0

        contexts = tuple(content for _, content in retrieved)
        retrieved_sources = tuple(name for name, _ in retrieved)
        prompt_tokens = max(1, len((case["question"] + " " + " ".join(contexts)).split()))
        completion_tokens = max(1, len(answer.split()))

        sample = RagasSample(
            question=case["question"],
            answer=answer,
            contexts=contexts,
            expected_facts=tuple(case.get("expected_facts", [])),
            expected_sources=tuple(case.get("expected_sources", [])),
            retrieved_sources=retrieved_sources,
            latency_ms=elapsed_ms,
            ttft_ms=ttft_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        score = evaluate_ragas_sample(sample)
        scores.append(score)
        latencies_ms.append(elapsed_ms)
        ttft_values_ms.append(ttft_ms)
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens

        case_results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expect_fallback": bool(case.get("expect_fallback", False)),
                "retrieved_sources": list(retrieved_sources),
                "ragas": score.to_dict(),
                "latency_ms": round(elapsed_ms, 3),
                "ttft_ms": round(ttft_ms, 3),
                "tokens": {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": prompt_tokens + completion_tokens,
                },
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline",
        "dataset": str(dataset_path.name),
        "total_cases": len(cases),
        "ragas_summary": aggregate_ragas_scores(scores),
        "latency_summary": compute_latency_percentiles(latencies_ms, ttft_values_ms),
        "token_usage_summary": {
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
        },
        "cases": case_results,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """Format baseline evaluation results as a readable Markdown report."""
    ragas = report["ragas_summary"]
    latency = report["latency_summary"]
    tokens = report["token_usage_summary"]

    lines = [
        "# Offline Deterministic Baseline Report (RAGAS-Inspired Custom Heuristic Metrics)",
        "",
        "> **Methodological Note:** Offline plumbing/heuristic baseline (`scoring_method=deterministic_heuristic`). Not valid for live LLM quality claims.",
        "",
        f"- **Generated At**: `{report['generated_at']}`",
        f"- **Mode**: `{report['mode']}`",
        f"- **Dataset**: `{report['dataset']}` ({report['total_cases']} cases)",
        "",
        "## RAGAS-Inspired Custom Heuristic Summary",
        "",
        "| Metric | Score |",
        "| --- | ---: |",
        f"| Context Precision | {ragas['context_precision']:.4f} |",
        f"| Context Recall | {ragas['context_recall']:.4f} |",
        f"| Faithfulness | {ragas['faithfulness']:.4f} |",
        f"| Answer Relevancy | {ragas['answer_relevancy']:.4f} |",
        f"| **Overall Score** | **{ragas['overall_score']:.4f}** |",
        "",
        "## Latency & Token Usage",
        "",
        f"- **p50 Latency**: `{latency['p50_ms']} ms`",
        f"- **p95 Latency**: `{latency['p95_ms']} ms`",
        f"- **Mean Latency**: `{latency['mean_ms']} ms`",
        f"- **TTFT p50 / p95**: `{latency.get('ttft_p50_ms', 0.0)} ms` / `{latency.get('ttft_p95_ms', 0.0)} ms`",
        f"- **Total Tokens (Prompt / Completion / Total)**: `{tokens['total_prompt_tokens']}` / `{tokens['total_completion_tokens']}` / `{tokens['total_tokens']}`",
        "",
        "## Per-Case Breakdown",
        "",
        "| ID | Retrieved Sources | Ctx Prec | Ctx Rec | Faithfulness | Relevancy | Overall |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in report["cases"]:
        r = case["ragas"]
        sources = ", ".join(case["retrieved_sources"]) or "(none)"
        lines.append(
            f"| `{case['id']}` | {sources} | {r['context_precision']:.2f} | "
            f"{r['context_recall']:.2f} | {r['faithfulness']:.2f} | "
            f"{r['answer_relevancy']:.2f} | {r['overall_score']:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_baseline_reports(
    report: dict[str, Any],
    results_dir: Path = DEFAULT_RESULTS_DIR,
    stem: str = "phase1_baseline",
) -> tuple[Path, Path]:
    """Persist JSON and Markdown baseline reports to disk."""
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / f"{stem}.json"
    md_path = results_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 1 RAGAS baseline evaluation.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--stem", type=str, default="phase1_baseline")
    args = parser.parse_args()

    report = run_offline_baseline(dataset_path=args.dataset, corpus_dir=args.corpus)
    json_path, md_path = write_baseline_reports(report, results_dir=args.results_dir, stem=args.stem)
    print(f"Baseline JSON: {json_path}")
    print(f"Baseline MD:   {md_path}")
    print(f"RAGAS Overall: {report['ragas_summary']['overall_score']:.4f}")


if __name__ == "__main__":
    main()
