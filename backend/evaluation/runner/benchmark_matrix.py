"""Benchmark Matrix Runner for Config A vs B vs C (T3.4).

Defines the three architectural configurations (excluding Semantic Cache completely):
- **Config A — Advanced RAG**:
  `HYBRID_SEARCH_ENABLED=true`, `RERANKER_ENABLED=true`, `CORRECTIVE_RAG_ENABLED=false`,
  `TOOL_USE_ENABLED=false`, `AGENTIC_MODE_ENABLED=false`.
- **Config B — Advanced RAG + Corrective RAG**:
  Same as Config A + `CORRECTIVE_RAG_ENABLED=true`.
- **Config C — Agentic + Excel SQL**:
  `TOOL_USE_ENABLED=true`, `AGENTIC_MODE_ENABLED=true`,
  `EXCEL_PARQUET_INGESTION_ENABLED=true`, `EXCEL_SQL_ENABLED=true`.

Dataset Allocation:
1. **Horizontal Comparison (A vs B vs C)** on `golden_set_v2.json` (Text RAG, Multi-turn, Out-of-scope Refusal).
2. **Specialized Agentic Evaluation (Config C only)** on `agent_sql_golden_set.json` (Inventory metadata, Excel DuckDB SQL, Hybrid SQL + RAG).
   *Note:* Config A and B are pure text-retrieval pipelines without inventory or SQL tools; forcing them onto `agent_sql_golden_set.json` would produce an artificial strawman comparison.

Execution Modes:
- `--offline-check`: Zero-network structural & pipeline validation (`valid_for_model_quality=False`).
- `--estimate-live`: Prints itemized Groq & Gemini API call estimates for human approval before `--live`.
- `--live --approve-live --qdrant-collection rag_documents_eval`: Executes live provider benchmarks against an isolated evaluation collection and writes `docs/evaluation/FINAL-EVALUATION-REPORT.md` with strictly separated Heuristic vs. `CustomLlmJudge` tables.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from evaluation.runner.baseline_eval import _load_corpus, _offline_retrieve
from evaluation.runner.eval_agent_cli import (
    DEFAULT_CORPUS_DIR,
    DEFAULT_SQL_DATASET,
    REPO_ROOT,
    run_offline_agent_smoke,
    validate_live_eval_collection,
)
from evaluation.scoring.agent_eval import OFFLINE_SMOKE_BANNER
from evaluation.scoring.ragas_metrics import (
    RagasSample,
    evaluate_dataset_samples,
)


EVAL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_V2_DATASET = EVAL_DIR / "datasets" / "golden_set_v2.json"
DEFAULT_FINAL_REPORT_PATH = REPO_ROOT / "docs" / "evaluation" / "FINAL-EVALUATION-REPORT.md"


@dataclass(frozen=True)
class BenchmarkConfig:
    """Architectural configuration entry in the Phase 3 Benchmark Matrix."""

    key: str
    name: str
    description: str
    flags: dict[str, bool]


BENCHMARK_CONFIGS: dict[str, BenchmarkConfig] = {
    "A": BenchmarkConfig(
        key="A",
        name="Config A — Advanced RAG",
        description="Hybrid search + Cross-encoder reranker without Corrective RAG or Agentic tools.",
        flags={
            "hybrid_search_enabled": True,
            "reranker_enabled": True,
            "corrective_rag_enabled": False,
            "tool_use_enabled": False,
            "agentic_mode_enabled": False,
            "excel_parquet_ingestion_enabled": False,
            "excel_sql_enabled": False,
            "semantic_cache_enabled": False,
        },
    ),
    "B": BenchmarkConfig(
        key="B",
        name="Config B — Advanced RAG + Corrective RAG",
        description="Config A plus lightweight LLM retrieval grading, 1-retry query correction, and strict safe fallback.",
        flags={
            "hybrid_search_enabled": True,
            "reranker_enabled": True,
            "corrective_rag_enabled": True,
            "tool_use_enabled": False,
            "agentic_mode_enabled": False,
            "excel_parquet_ingestion_enabled": False,
            "excel_sql_enabled": False,
            "semantic_cache_enabled": False,
        },
    ),
    "C": BenchmarkConfig(
        key="C",
        name="Config C — Agentic + Excel SQL",
        description="Iterative Agentic loop with count_documents, list_documents, rag_search, and DuckDB run_sql over Parquet.",
        flags={
            "hybrid_search_enabled": True,
            "reranker_enabled": True,
            "corrective_rag_enabled": False,
            "tool_use_enabled": True,
            "agentic_mode_enabled": True,
            "excel_parquet_ingestion_enabled": True,
            "excel_sql_enabled": True,
            "semantic_cache_enabled": False,
        },
    ),
}


def estimate_live_provider_calls(
    *,
    v2_dataset_path: Path = DEFAULT_V2_DATASET,
    sql_dataset_path: Path = DEFAULT_SQL_DATASET,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
    include_llm_judge: bool = True,
) -> dict[str, Any]:
    """Compute transparent upper-bound Groq LLM & Gemini Embedding API call counts before --live."""
    v2_cases = json.loads(v2_dataset_path.read_text(encoding="utf-8")).get("cases", [])
    sql_cases = json.loads(sql_dataset_path.read_text(encoding="utf-8")).get("cases", [])
    corpus_files = sorted(list(corpus_dir.glob("*.md")) + list(corpus_dir.glob("*.txt")))

    n_v2 = len(v2_cases)
    n_v2_history = sum(1 for c in v2_cases if c.get("history"))
    n_v2_oos = sum(1 for c in v2_cases if c.get("expect_refusal"))
    n_sql = len(sql_cases)
    n_sql_hybrid = sum(1 for c in sql_cases if "rag_search" in (c.get("expected_tools") or []))

    # Groq LLM call breakdown (upper-bound estimate):
    # - Config A on golden_set_v2: history query rewrite (n_v2_history) + 1 final generation per case (n_v2)
    groq_config_a = n_v2_history + n_v2
    # - Config B on golden_set_v2: history rewrite + 1 grader call/case + up to 1 query-corrector retry on OOS/ambiguous + 1 generation on in-scope
    groq_config_b = n_v2_history + n_v2 + n_v2_oos + (n_v2 - n_v2_oos)
    # - Config C on golden_set_v2: ~2 agent steps per case (plan tool call -> final grounded synthesis)
    groq_config_c_v2 = n_v2 * 2
    # - Config C on agent_sql_golden_set: 2 steps for single-tool cases, up to 3 steps for hybrid cases
    groq_config_c_sql = (n_sql - n_sql_hybrid) * 2 + (n_sql_hybrid * 3)
    # - Optional CustomLlmJudge: 3 configs * n_v2 cases
    groq_llm_judge = (3 * n_v2) if include_llm_judge else 0

    total_groq_calls = (
        groq_config_a + groq_config_b + groq_config_c_v2 + groq_config_c_sql + groq_llm_judge
    )

    # Gemini Embedding call breakdown (`gemini-embedding-001`):
    # - One-time isolated corpus indexing into `rag_documents_eval` (text files + 2 workbooks)
    gemini_corpus_index = len(corpus_files) + 2
    # - Config A query embeddings (1 query + optional multi-query expansion up to 2x)
    gemini_config_a = n_v2 * 2
    # - Config B query embeddings (Config A + 1 re-retrieval embedding per corrective retry)
    gemini_config_b = (n_v2 * 2) + n_v2_oos
    # - Config C `rag_search` embeddings (n_v2 cases + hybrid SQL+RAG cases)
    gemini_config_c = n_v2 + n_sql_hybrid

    total_gemini_calls = (
        gemini_corpus_index + gemini_config_a + gemini_config_b + gemini_config_c
    )

    return {
        "datasets": {
            "golden_set_v2_cases": n_v2,
            "golden_set_v2_multi_turn_cases": n_v2_history,
            "golden_set_v2_out_of_scope_cases": n_v2_oos,
            "agent_sql_golden_set_cases": n_sql,
            "agent_sql_hybrid_cases": n_sql_hybrid,
            "corpus_text_files": len(corpus_files),
        },
        "include_llm_judge": include_llm_judge,
        "groq_breakdown": {
            "config_a_v2": groq_config_a,
            "config_b_v2": groq_config_b,
            "config_c_v2": groq_config_c_v2,
            "config_c_agent_sql": groq_config_c_sql,
            "custom_llm_judge": groq_llm_judge,
        },
        "gemini_embedding_breakdown": {
            "isolated_corpus_indexing": gemini_corpus_index,
            "config_a_queries": gemini_config_a,
            "config_b_queries": gemini_config_b,
            "config_c_rag_search": gemini_config_c,
        },
        "estimated_groq_calls": total_groq_calls,
        "estimated_gemini_embedding_calls": total_gemini_calls,
    }


def run_offline_matrix_check(
    *,
    v2_dataset_path: Path = DEFAULT_V2_DATASET,
    sql_dataset_path: Path = DEFAULT_SQL_DATASET,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
) -> dict[str, Any]:
    """Validate datasets, config flags, refusal separation, and DuckDB plumbing without network."""
    if not v2_dataset_path.is_file():
        raise FileNotFoundError(f"Missing v2 dataset: {v2_dataset_path}")
    if not sql_dataset_path.is_file():
        raise FileNotFoundError(f"Missing SQL dataset: {sql_dataset_path}")

    for cfg in BENCHMARK_CONFIGS.values():
        if cfg.flags.get("semantic_cache_enabled", False):
            raise ValueError(f"Semantic cache must be disabled in {cfg.name}.")

    v2_payload = json.loads(v2_dataset_path.read_text(encoding="utf-8"))
    v2_cases = v2_payload.get("cases", [])
    corpus = _load_corpus(corpus_dir)

    offline_v2_samples: list[RagasSample] = []
    for case in v2_cases:
        for expected_src in case.get("expected_sources", []):
            if expected_src not in corpus:
                raise FileNotFoundError(f"Corpus file '{expected_src}' missing for case {case['id']}.")

        t0 = time.perf_counter()
        if case.get("expect_refusal"):
            retrieved: list[tuple[str, str]] = []
            answer = "Không tìm thấy thông tin về nội dung này trong tài liệu đã tải lên."
        else:
            retrieved = _offline_retrieve(case["question"], corpus, top_k=2)
            answer = (
                " ".join(content.strip() for _, content in retrieved[:1])
                if retrieved
                else "Không tìm thấy thông tin trong tài liệu đã tải lên."
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        offline_v2_samples.append(
            RagasSample(
                question=case["question"],
                answer=answer,
                contexts=tuple(content for _, content in retrieved),
                expected_facts=tuple(case.get("expected_facts", [])),
                expected_sources=tuple(case.get("expected_sources", [])),
                retrieved_sources=tuple(name for name, _ in retrieved),
                ground_truth=case.get("ground_truth", ""),
                latency_ms=elapsed_ms,
                ttft_ms=elapsed_ms * 0.5,
                prompt_tokens=64,
                completion_tokens=24,
                expect_refusal=bool(case.get("expect_refusal", False)),
            )
        )

    v2_smoke_report = evaluate_dataset_samples(
        offline_v2_samples,
        scoring_method="deterministic_heuristic",
    )
    agent_smoke_report = run_offline_agent_smoke(
        dataset_path=sql_dataset_path,
        corpus_dir=corpus_dir,
    )

    return {
        "status": "PASS",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "run_mode": "offline_check",
        "valid_for_model_quality": False,
        "banner": OFFLINE_SMOKE_BANNER,
        "configs": {key: cfg.flags for key, cfg in BENCHMARK_CONFIGS.items()},
        "excluded_features": ["semantic_cache"],
        "horizontal_dataset": v2_dataset_path.name,
        "horizontal_dataset_configs": ["A", "B", "C"],
        "specialized_sql_dataset": sql_dataset_path.name,
        "specialized_sql_configs": ["C"],
        "specialized_exclusion_reason": (
            "Config A and Config B are text-only RAG pipelines without metadata inventory or "
            "DuckDB SQL tools; agent_sql_golden_set.json is evaluated strictly on Config C."
        ),
        "text_rag_offline_smoke": v2_smoke_report.to_dict(),
        "agent_sql_offline_smoke_summary": agent_smoke_report["summary"],
    }


def render_final_evaluation_markdown(live_payload: dict[str, Any]) -> str:
    """Render method-pure Markdown report separating Heuristic vs. CustomLlmJudge and A/B/C vs. C."""
    if not live_payload.get("valid_for_model_quality"):
        raise ValueError(
            "Refusing to render FINAL-EVALUATION-REPORT.md from offline/plumbing data."
        )

    lines = [
        "# RAG Workspace — Final Benchmark & Agent Evaluation Report",
        "",
        f"- **Generated At**: `{live_payload['generated_at']}`",
        f"- **Run Mode**: `live_eval` (Isolated Qdrant Collection: `{live_payload['qdrant_collection']}`)",
        "- **Metric Methodology**: **RAGAS-Inspired Custom Metrics** (`deterministic_heuristic` and `CustomLlmJudge` reported in strictly separate tables — NOT the official `ragas` PyPI library, and zero heuristic fallback on judge errors).",
        "- **Semantic Cache**: Explicitly disabled (`SEMANTIC_CACHE_ENABLED=false`) across all configurations.",
        "",
        "## 1. Horizontal Comparison (Config A vs B vs C) on `golden_set_v2.json` — Deterministic Heuristic",
        "",
        "| Config | In-Scope Ctx Prec | In-Scope Ctx Rec | In-Scope Faithfulness | In-Scope Answer Rel | Overall (In-Scope) | Correct Refusal Rate (Out-of-Scope) | Groundedness Supplement | p50 (ms) | p95 (ms) | Total Tokens |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ("A", "B", "C"):
        entry = live_payload["horizontal_heuristic"][key]
        s = entry["in_scope_summary"]
        lat = entry["latency_summary"]
        tok = entry["token_usage_summary"]
        supp = entry["groundedness_supplement"]
        ref_rate = entry["correct_refusal_rate"]
        ref_str = f"{ref_rate:.4f}" if ref_rate is not None else "N/A"
        lines.append(
            f"| **{BENCHMARK_CONFIGS[key].name}** | {s['context_precision']:.4f} | {s['context_recall']:.4f} | "
            f"{s['faithfulness']:.4f} | {s['answer_relevancy']:.4f} | **{s['overall_score']:.4f}** | "
            f"{ref_str} | {supp['mean_support_ratio']:.4f} | {lat['p50_ms']} | {lat['p95_ms']} | {tok['total_tokens']} |"
        )

    if live_payload.get("horizontal_llm_judge"):
        lines.extend(
            [
                "",
                "## 2. Horizontal Comparison (Config A vs B vs C) on `golden_set_v2.json` — `CustomLlmJudge`",
                "",
                "| Config | Valid In-Scope | Judge Errors | Ctx Prec | Ctx Rec | Faithfulness | Answer Rel | Overall (In-Scope) | Correct Refusal Rate |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key in ("A", "B", "C"):
            entry = live_payload["horizontal_llm_judge"][key]
            s = entry["in_scope_summary"]
            ref_rate = entry["correct_refusal_rate"]
            ref_str = f"{ref_rate:.4f}" if ref_rate is not None else "N/A"
            lines.append(
                f"| **{BENCHMARK_CONFIGS[key].name}** | {entry['valid_in_scope_count']}/{entry['in_scope_count']} | "
                f"{entry['judge_error_count']} | {s['context_precision']:.4f} | {s['context_recall']:.4f} | "
                f"{s['faithfulness']:.4f} | {s['answer_relevancy']:.4f} | **{s['overall_score']:.4f}** | {ref_str} |"
            )

    c_sql = live_payload["specialized_config_c_sql"]["summary"]
    lines.extend(
        [
            "",
            "## 3. Specialized Agent & Excel SQL Trajectory (Config C Only) on `agent_sql_golden_set.json`",
            "",
            "> **Architectural Scope Note:** Config A and Config B do not expose `count_documents`, `list_documents`, or `run_sql` tools and are therefore intentionally excluded from this table.",
            "",
            "| Metric | Config C (`Agentic + Excel SQL`) |",
            "| --- | ---: |",
            f"| Route Accuracy | {c_sql['route_accuracy']:.4f} |",
            f"| Tool Selection Precision | {c_sql['tool_selection_precision']:.4f} |",
            f"| Tool Selection Recall | {c_sql['tool_selection_recall']:.4f} |",
            f"| SQL Guard Pass Rate | {c_sql['sql_guard_pass_rate']:.4f} |",
            f"| SQL Execution Accuracy | {c_sql['sql_execution_accuracy']:.4f} |",
            f"| Citation Validity Rate | {c_sql['citation_validity_rate']:.4f} |",
            f"| Avg Agent Steps | {c_sql['avg_agent_steps']:.2f} |",
            f"| Latency p50 / p95 (ms) | {c_sql['p50_ms']} / {c_sql['p95_ms']} |",
            f"| Total Tokens | {c_sql['total_tokens']} |",
            "",
        ]
    )
    return "\n".join(lines)


async def _execute_live_benchmark_matrix(
    *,
    qdrant_collection: str,
    include_llm_judge: bool,
) -> dict[str, Any]:
    """Execute live provider benchmark against an isolated Qdrant collection (`rag_documents_eval`)."""
    from langchain_core.documents import Document

    from app.chat.history import HistoryTurn, TurnMessage
    from app.chat.orchestrator import ChatOrchestrator
    from app.chat.pipeline import generate_prepared_answer, prepare_rag_request
    from app.documents.excel.sql_service import ExcelSqlService
    from app.documents.queries import DocumentQueries
    from app.infrastructure.duckdb_executor import DuckDBSqlExecutor
    from app.infrastructure.qdrant_client import get_qdrant_client
    from app.infrastructure.qdrant_index import QdrantVectorIndex
    from app.rag.embeddings import get_embeddings
    from app.rag.llm import get_grader_llm, get_llm
    from app.rag.reranker import get_reranker
    from app.rag.retriever import retrieve_relevant_chunks
    from app.rag.splitter import split_documents
    from app.shared.config import settings
    from evaluation.runner.eval_agent_cli import _build_offline_eval_fixture
    from evaluation.scoring.agent_eval import (
        AgentEvalCase,
        AgentTurnObservation,
        evaluate_agent_trajectory,
    )
    from evaluation.scoring.llm_judge import CustomLlmJudge

    safe_collection = validate_live_eval_collection(qdrant_collection)
    v2_cases = json.loads(DEFAULT_V2_DATASET.read_text(encoding="utf-8"))["cases"]
    sql_cases = json.loads(DEFAULT_SQL_DATASET.read_text(encoding="utf-8"))["cases"]

    with tempfile.TemporaryDirectory(prefix="rag_live_eval_parquet_") as tmp_dir:
        parquet_root = Path(tmp_dir)
        repo, corpus_texts, _ = _build_offline_eval_fixture(
            DEFAULT_CORPUS_DIR,
            sql_cases,
            parquet_root,
        )
        text_docs = [
            d for d in repo.list_documents(limit=500) if Path(d.file_name).suffix.lower() in (".md", ".txt")
        ]
        active_version_ids = tuple(
            d.active_version_id for d in repo.list_documents(limit=500) if d.active_version_id
        )

        qdrant_client = get_qdrant_client()
        embeddings = get_embeddings()
        with patch.object(settings, "qdrant_collection", safe_collection):
            vector_index = QdrantVectorIndex(
                client=qdrant_client,
                embeddings=embeddings,
                collection_name=safe_collection,
            )
            # Index synthetic text corpus into isolated eval collection
            for doc_rec in text_docs:
                raw_text = corpus_texts[doc_rec.file_name]
                lc_doc = Document(
                    page_content=raw_text,
                    metadata={
                        "document_id": doc_rec.document_id,
                        "version_id": doc_rec.active_version_id,
                        "file_name": doc_rec.file_name,
                    },
                )
                chunks = split_documents([lc_doc])
                vector_index.index_version_chunks(
                    document_id=doc_rec.document_id,
                    version_id=str(doc_rec.active_version_id),
                    file_name=doc_rec.file_name,
                    chunks=chunks,
                )

            def _load_local_parquet(parquet_key: str) -> bytes:
                return (parquet_root / parquet_key).read_bytes()

            executor = DuckDBSqlExecutor(
                storage_backend="local",
                local_parquet_loader=_load_local_parquet,
            )
            sql_service = ExcelSqlService(repository=repo, executor=executor)
            queries = DocumentQueries(repo)  # type: ignore[arg-type]

            def _live_rag_search_fn(query: str, top_k: int = 4) -> list[Document]:
                retrieved = retrieve_relevant_chunks(
                    query,
                    qdrant_client=qdrant_client,
                    active_version_ids=active_version_ids,
                    k=max(top_k, settings.retrieval_top_k),
                )
                if settings.reranker_enabled and retrieved:
                    return get_reranker().rerank(query, retrieved, top_n=top_k)
                return retrieved[:top_k]

            samples_by_cfg: dict[str, list[RagasSample]] = {"A": [], "B": [], "C": []}

            for cfg_key in ("A", "B", "C"):
                cfg = BENCHMARK_CONFIGS[cfg_key]
                with ExitStack() as stack:
                    for flag_name, flag_val in cfg.flags.items():
                        stack.enter_context(patch.object(settings, flag_name, flag_val))
                    stack.enter_context(patch.object(settings, "storage_backend", "local"))

                    for case in v2_cases:
                        t0 = time.perf_counter()
                        if cfg_key in ("A", "B"):
                            prepared = await prepare_rag_request(
                                case["question"],
                                qdrant_client=qdrant_client,
                                active_version_ids=active_version_ids,
                            )
                            gen = await generate_prepared_answer(prepared)
                            answer = gen["answer"]
                            sources = gen.get("sources") or []
                            usage = gen.get("usage") or {}
                            contexts = tuple(
                                str(s.get("content") or s.get("snippet") or s.get("file_name") or "")
                                for s in sources
                            )
                        else:
                            orchestrator = ChatOrchestrator(
                                queries=queries,
                                tools_enabled=True,
                                agentic_mode=True,
                                excel_sql_enabled=True,
                                sql_service=sql_service,
                                rag_search_fn=_live_rag_search_fn,
                                tenant_id="default",
                            )
                            plan = await orchestrator.prepare_plan(case["question"], qdrant_client=qdrant_client)
                            gen = await orchestrator.generate_json(plan)
                            answer = gen["answer"]
                            sources = gen.get("sources") or []
                            usage = gen.get("usage") or {}
                            contexts = tuple(str(s.get("file_name") or "") for s in sources)

                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        samples_by_cfg[cfg_key].append(
                            RagasSample(
                                question=case["question"],
                                answer=answer,
                                contexts=contexts,
                                expected_facts=tuple(case.get("expected_facts", [])),
                                expected_sources=tuple(case.get("expected_sources", [])),
                                retrieved_sources=tuple(
                                    str(s.get("file_name")) for s in sources if s.get("file_name")
                                ),
                                ground_truth=case.get("ground_truth", ""),
                                latency_ms=elapsed_ms,
                                prompt_tokens=int(usage.get("input_tokens", 0) or 0),
                                completion_tokens=int(usage.get("output_tokens", 0) or 0),
                                expect_refusal=bool(case.get("expect_refusal", False)),
                            )
                        )

            # Config C specialized SQL & hybrid benchmark
            sql_eval_cases: list[AgentEvalCase] = []
            sql_observations: list[AgentTurnObservation] = []
            allowed_views = tuple(b.view_name for b in sql_service.list_authorized_tables(tenant_id="default"))

            with ExitStack() as stack:
                for flag_name, flag_val in BENCHMARK_CONFIGS["C"].flags.items():
                    stack.enter_context(patch.object(settings, flag_name, flag_val))
                stack.enter_context(patch.object(settings, "storage_backend", "local"))

                for raw in sql_cases:
                    sql_eval_cases.append(
                        AgentEvalCase(
                            case_id=raw["id"],
                            question=raw["question"],
                            expected_route=raw.get("expected_route", "AGENTIC"),
                            expected_tools=tuple(raw.get("expected_tools", [])),
                            expected_facts=tuple(raw.get("expected_facts", [])),
                            expect_sql=bool(raw.get("expect_sql", False)),
                            ground_truth=raw.get("ground_truth", ""),
                        )
                    )
                    captured_sql: list[str] = []
                    captured_tools: list[str] = []
                    orig_exec_query = sql_service.execute_query

                    def _spy_exec_query(*, sql: str, **kw: Any):
                        captured_sql.append(sql)
                        captured_tools.append("run_sql")
                        return orig_exec_query(sql=sql, **kw)

                    t0 = time.perf_counter()
                    with patch.object(sql_service, "execute_query", side_effect=_spy_exec_query):
                        orchestrator = ChatOrchestrator(
                            queries=queries,
                            tools_enabled=True,
                            agentic_mode=True,
                            excel_sql_enabled=True,
                            sql_service=sql_service,
                            rag_search_fn=_live_rag_search_fn,
                            tenant_id="default",
                        )
                        plan = await orchestrator.prepare_plan(raw["question"], qdrant_client=qdrant_client)
                        gen = await orchestrator.generate_json(plan)
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    usage = gen.get("usage") or {}
                    sources = gen.get("sources") or []
                    if any(s.get("chunk_id") for s in sources) and "rag_search" not in captured_tools:
                        captured_tools.append("rag_search")

                    sql_observations.append(
                        AgentTurnObservation(
                            case_id=raw["id"],
                            actual_route=plan.route,
                            called_tools=tuple(captured_tools),
                            generated_sql=tuple(captured_sql),
                            allowed_views=allowed_views,
                            answer=gen["answer"],
                            citations_valid=bool(sources) if raw.get("expect_sql") else True,
                            agent_steps=max(1, len(plan.ledger.entries)),
                            latency_ms=elapsed_ms,
                            prompt_tokens=int(usage.get("input_tokens", 0) or 0),
                            completion_tokens=int(usage.get("output_tokens", 0) or 0),
                        )
                    )

            horizontal_heuristic = {
                k: evaluate_dataset_samples(
                    samples_by_cfg[k],
                    scoring_method="deterministic_heuristic",
                ).to_dict()
                for k in ("A", "B", "C")
            }

            horizontal_llm_judge: dict[str, Any] | None = None
            if include_llm_judge:
                judge = CustomLlmJudge(llm=get_grader_llm() or get_llm(), max_retries=1)
                horizontal_llm_judge = {
                    k: evaluate_dataset_samples(
                        samples_by_cfg[k],
                        scoring_method="custom_llm_judge",
                        custom_judge=judge,
                    ).to_dict()
                    for k in ("A", "B", "C")
                }

            c_sql_report = evaluate_agent_trajectory(
                sql_eval_cases,
                sql_observations,
                run_mode="live_eval",
            ).to_dict()

            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "run_mode": "live_eval",
                "valid_for_model_quality": True,
                "qdrant_collection": safe_collection,
                "horizontal_heuristic": horizontal_heuristic,
                "horizontal_llm_judge": horizontal_llm_judge,
                "specialized_config_c_sql": c_sql_report,
            }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 3 Benchmark Matrix Runner (Config A vs B vs C)."
    )
    parser.add_argument("--offline-check", action="store_true", help="Run zero-network validation & plumbing check.")
    parser.add_argument("--estimate-live", action="store_true", help="Print provider API call estimates before --live.")
    parser.add_argument("--live", action="store_true", help="Execute live LLM + Qdrant benchmark on isolated collection.")
    parser.add_argument("--approve-live", action="store_true", help="Confirm user approval for live provider calls.")
    parser.add_argument("--no-llm-judge", action="store_true", help="Skip CustomLlmJudge pass during --live.")
    parser.add_argument("--qdrant-collection", type=str, default="rag_documents_eval")
    parser.add_argument("--report-out", type=Path, default=DEFAULT_FINAL_REPORT_PATH)
    args = parser.parse_args()

    include_judge = not args.no_llm_judge

    if args.estimate_live or (not args.offline_check and not args.live):
        estimate = estimate_live_provider_calls(include_llm_judge=include_judge)
        print(json.dumps(estimate, indent=2, ensure_ascii=False))
        return

    if args.offline_check:
        check = run_offline_matrix_check()
        estimate = estimate_live_provider_calls(include_llm_judge=include_judge)
        print(f"[{check['banner']}]")
        print(
            json.dumps(
                {
                    "status": check["status"],
                    "valid_for_model_quality": check["valid_for_model_quality"],
                    "horizontal_dataset": check["horizontal_dataset"],
                    "horizontal_dataset_configs": check["horizontal_dataset_configs"],
                    "specialized_sql_dataset": check["specialized_sql_dataset"],
                    "specialized_sql_configs": check["specialized_sql_configs"],
                    "text_rag_in_scope_summary": check["text_rag_offline_smoke"]["in_scope_summary"],
                    "text_rag_correct_refusal_rate": check["text_rag_offline_smoke"]["correct_refusal_rate"],
                    "agent_sql_offline_smoke_summary": check["agent_sql_offline_smoke_summary"],
                    "live_call_estimate": {
                        "estimated_groq_calls": estimate["estimated_groq_calls"],
                        "estimated_gemini_embedding_calls": estimate["estimated_gemini_embedding_calls"],
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    safe_collection = validate_live_eval_collection(args.qdrant_collection)
    if not args.approve_live:
        est = estimate_live_provider_calls(include_llm_judge=include_judge)
        raise SystemExit(
            f"BLOCKED: --live requires --approve-live after user approval.\n"
            f"Target collection: {safe_collection}\n"
            f"Estimated Groq calls: {est['estimated_groq_calls']}\n"
            f"Estimated Gemini Embedding calls: {est['estimated_gemini_embedding_calls']}"
        )

    live_payload = asyncio.run(
        _execute_live_benchmark_matrix(
            qdrant_collection=safe_collection,
            include_llm_judge=include_judge,
        )
    )
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(render_final_evaluation_markdown(live_payload), encoding="utf-8")
    json_out = EVAL_DIR / "results" / "phase3_live_benchmark_matrix.json"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(live_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Final Evaluation Report written to: {args.report_out}")
    print(f"Raw Live JSON written to:           {json_out}")


if __name__ == "__main__":
    main()
