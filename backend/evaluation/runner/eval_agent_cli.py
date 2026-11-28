"""CLI & Runner for Agent + Excel SQL Trajectory Evaluation (T3.3).

Supports two strictly separated execution modes:
- `--mode offline_smoke`: Deterministic scripted tool-calling model wired into the real
  `ChatOrchestrator` + `ExcelSqlService` + `sql_guard` + `DuckDBSqlExecutor` + `DocumentQueries`
  pipeline over synthetic local Parquet tables (zero network, CI-safe). Explicitly stamped
  `OFFLINE_PLUMBING_CHECK — NOT VALID FOR MODEL QUALITY CLAIMS`.
- `--mode live_eval`: Executes a live tool-capable LLM against an isolated evaluation
  collection (`rag_documents_eval`). Hard-blocks `rag_documents` to protect production data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.chat.orchestrator import ChatOrchestrator
from app.documents.excel.sql_service import ExcelSqlService
from app.documents.excel.tabular import extract_workbook_tables
from app.documents.models import (
    DocumentRecord,
    DocumentStatus,
    DocumentTableCatalogRecord,
    TableColumnSchema,
)
from app.documents.queries import DocumentQueries
from app.infrastructure.duckdb_executor import DuckDBSqlExecutor
from app.shared.config import settings
from evaluation.scoring.agent_eval import (
    AgentEvalCase,
    AgentTurnObservation,
    evaluate_agent_trajectory,
)
from evaluation.scoring.metrics import _content_tokens


EVAL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EVAL_DIR.parent.parent
DEFAULT_SQL_DATASET = EVAL_DIR / "datasets" / "agent_sql_golden_set.json"
DEFAULT_CORPUS_DIR = EVAL_DIR / "datasets" / "corpus"
DEFAULT_RESULTS_DIR = EVAL_DIR / "results"

FORBIDDEN_PRODUCTION_COLLECTIONS = frozenset({"rag_documents"})


def validate_live_eval_collection(collection_name: str) -> str:
    """Enforce that live evaluation never targets the production Qdrant collection."""
    normalized = (collection_name or "").strip()
    if not normalized:
        raise ValueError("Qdrant evaluation collection name must not be empty.")
    if normalized.lower() in FORBIDDEN_PRODUCTION_COLLECTIONS:
        raise ValueError(
            f"Refusing to run live evaluation against production collection '{normalized}'. "
            "Use an isolated collection such as 'rag_documents_eval'."
        )
    return normalized


def _deterministic_uuid(seed_index: int) -> str:
    return str(UUID(int=seed_index, version=4))


class _InMemoryEvalDocumentRepository:
    """Offline repository adapter implementing DocumentQueries + ExcelSqlService read contracts."""

    def __init__(
        self,
        documents: list[DocumentRecord],
        catalog_records: list[DocumentTableCatalogRecord],
    ) -> None:
        self._documents = list(documents)
        self._catalog = list(catalog_records)

    def count_documents_for_tools(self, *, include_deleted: bool = False) -> int:
        if include_deleted:
            return len(self._documents)
        return sum(
            1
            for doc in self._documents
            if doc.status != DocumentStatus.DELETED and doc.deleted_at is None
        )

    def list_documents_for_tools(
        self,
        *,
        include_deleted: bool = False,
        offset: int = 0,
        limit: int = 10,
    ) -> list[DocumentRecord]:
        items = [
            doc
            for doc in self._documents
            if include_deleted or (doc.status != DocumentStatus.DELETED and doc.deleted_at is None)
        ]
        items.sort(key=lambda d: (d.created_at, d.document_id), reverse=True)
        return items[offset : offset + limit]

    def list_documents(
        self,
        *,
        include_deleted: bool = False,
        offset: int = 0,
        limit: int = 500,
    ) -> list[DocumentRecord]:
        return self.list_documents_for_tools(
            include_deleted=include_deleted,
            offset=offset,
            limit=limit,
        )

    def list_tables_for_versions(
        self,
        version_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> list[DocumentTableCatalogRecord]:
        allowed = set(version_ids)
        return [
            rec
            for rec in self._catalog
            if rec.version_id in allowed and rec.tenant_id == tenant_id
        ]


class _ScriptedOfflineAgentModel:
    """Deterministic offline model driving real tool execution for CI plumbing checks."""

    def __init__(self, case_spec: dict[str, Any]) -> None:
        self._case = case_spec
        self.step_calls = 0
        self.generated_sql: list[str] = []
        self.called_tools: list[str] = []

    def bind_tools(self, schemas: list[dict[str, Any]], tool_choice: str = "auto") -> _ScriptedOfflineAgentModel:
        return self

    async def ainvoke(self, messages: list[BaseMessage], **kwargs: Any) -> AIMessage:
        self.step_calls += 1
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]

        if not tool_msgs:
            planned_calls: list[dict[str, Any]] = []
            for idx, tool_name in enumerate(self._case["expected_tools"], start=1):
                if tool_name == "count_documents":
                    args: dict[str, Any] = {"include_deleted": False}
                elif tool_name == "list_documents":
                    args = {"include_deleted": False, "offset": 0, "limit": 10}
                elif tool_name == "run_sql":
                    sql_stmt = str(self._case["verification_sql"])
                    args = {"sql": sql_stmt}
                    self.generated_sql.append(sql_stmt)
                elif tool_name == "rag_search":
                    args = {
                        "query": str(self._case.get("rag_search_query") or self._case["question"]),
                        "top_k": 3,
                    }
                else:
                    raise ValueError(f"Unsupported offline tool in golden case: {tool_name}")
                self.called_tools.append(tool_name)
                planned_calls.append({"id": f"call_{idx}", "name": tool_name, "args": args})

            return AIMessage(
                content="",
                tool_calls=planned_calls,
                usage_metadata={"input_tokens": 120, "output_tokens": 25, "total_tokens": 145},
            )

        # Synthesize final answer directly from real executed ToolMessage envelopes!
        extracted_pieces: list[str] = []
        has_source_tools = False
        for t_msg in tool_msgs:
            envelope = json.loads(str(t_msg.content))
            if not envelope.get("ok"):
                raise RuntimeError(f"Tool {t_msg.name} failed in offline smoke: {envelope}")
            data = envelope.get("data", {})
            if t_msg.name == "count_documents":
                extracted_pieces.append(f"Kho tri thức hiện có {data['count']} tài liệu đang hoạt động.")
            elif t_msg.name == "list_documents":
                names = ", ".join(item["file_name"] for item in data.get("items", []))
                extracted_pieces.append(f"Các tài liệu hiện có gồm: {names}.")
            elif t_msg.name == "run_sql":
                has_source_tools = True
                rows = data.get("rows", [])
                first_scalar = next(iter(rows[0].values())) if rows and isinstance(rows[0], dict) and rows[0] else ""
                extracted_pieces.append(f"Kết quả truy vấn SQL trên bảng dữ liệu là {first_scalar}.")
            elif t_msg.name == "rag_search":
                has_source_tools = True
                hits = data.get("hits", [])
                joined = " ".join(hit.get("snippet", "") for hit in hits)
                extracted_pieces.append(joined)

        citation_suffix = " [1]" if has_source_tools else ""
        final_text = " ".join(extracted_pieces).strip() + citation_suffix
        return AIMessage(
            content=final_text,
            usage_metadata={"input_tokens": 180, "output_tokens": 40, "total_tokens": 220},
        )


def _drive_pure_async_coro(coro: Any) -> Any:
    """Execute a pure coroutine synchronously without opening loopback OS sockets."""
    async def _sync_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    async def _sync_wait_for(fut: Any, timeout: float | None = None) -> Any:
        return await fut

    with (
        patch.object(asyncio, "to_thread", _sync_to_thread),
        patch.object(asyncio, "wait_for", _sync_wait_for),
    ):
        try:
            coro.send(None)
        except StopIteration as stop:
            return stop.value
        finally:
            coro.close()
    raise RuntimeError("Coroutine yielded an unexpected non-synchronous future in offline smoke.")


def _build_offline_eval_fixture(
    corpus_dir: Path,
    sql_cases: list[dict[str, Any]],
    parquet_dir: Path,
) -> tuple[_InMemoryEvalDocumentRepository, dict[str, str], dict[str, bytes]]:
    """Build synthetic document metadata, extracted Parquet files, and text corpus map."""
    documents: list[DocumentRecord] = []
    catalog_records: list[DocumentTableCatalogRecord] = []
    corpus_texts: dict[str, str] = {}
    parquet_bytes_by_key: dict[str, bytes] = {}
    seed = 100

    for path in sorted(list(corpus_dir.glob("*.md")) + list(corpus_dir.glob("*.txt"))):
        corpus_texts[path.name] = path.read_text(encoding="utf-8")
        seed += 1
        doc_id = _deterministic_uuid(seed)
        seed += 1
        ver_id = _deterministic_uuid(seed)
        documents.append(
            DocumentRecord(
                document_id=doc_id,
                file_name=path.name,
                active_version_id=ver_id,
                status=DocumentStatus.INDEXED,
                tenant_id="default",
            )
        )

    seen_workbooks: list[str] = []
    for case in sql_cases:
        wb_rel = case.get("workbook_path")
        if wb_rel and wb_rel not in seen_workbooks:
            seen_workbooks.append(wb_rel)

    for wb_rel in seen_workbooks:
        wb_path = REPO_ROOT / wb_rel
        raw_bytes = wb_path.read_bytes()
        extracted_tables = extract_workbook_tables(raw_bytes)
        seed += 1
        doc_id = _deterministic_uuid(seed)
        seed += 1
        ver_id = _deterministic_uuid(seed)
        documents.append(
            DocumentRecord(
                document_id=doc_id,
                file_name=wb_path.name,
                active_version_id=ver_id,
                status=DocumentStatus.INDEXED,
                tenant_id="default",
            )
        )
        for tbl in extracted_tables:
            seed += 1
            cat_id = _deterministic_uuid(seed)
            parquet_key = f"default/{doc_id}/{ver_id}/tables/{tbl.table_name}.parquet"
            target_file = parquet_dir / parquet_key
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_bytes(tbl.parquet_bytes)
            parquet_bytes_by_key[parquet_key] = tbl.parquet_bytes

            catalog_records.append(
                DocumentTableCatalogRecord(
                    catalog_id=cat_id,
                    tenant_id="default",
                    document_id=doc_id,
                    version_id=ver_id,
                    table_name=tbl.table_name,
                    sheet_name=tbl.sheet_name,
                    parquet_key=parquet_key,
                    row_count=tbl.row_count,
                    columns=[
                        TableColumnSchema(
                            name=col.name,
                            original_name=col.original_name,
                            type=col.data_type,
                            nullable=col.nullable,
                            description=col.description,
                            has_formula_values=col.has_formula_values,
                            is_free_text=col.is_free_text,
                        )
                        for col in tbl.columns
                    ],
                    sample_rows=list(tbl.sample_rows),
                    has_formula_values=tbl.has_formula_values,
                )
            )

    repo = _InMemoryEvalDocumentRepository(documents, catalog_records)
    return repo, corpus_texts, parquet_bytes_by_key


def _make_offline_rag_search_fn(corpus_texts: dict[str, str]):
    from app.rag.splitter import split_documents

    indexed_chunks: list[Document] = []
    for name, text in corpus_texts.items():
        base_doc = Document(
            page_content=text,
            metadata={
                "document_id": f"doc-{name}",
                "version_id": f"ver-{name}",
                "file_name": name,
            },
        )
        for idx, chunk in enumerate(split_documents([base_doc])):
            chunk.metadata["chunk_id"] = f"offline-{name}-{idx}"
            chunk.metadata["chunk_index"] = idx
            indexed_chunks.append(chunk)

    def _retrieve(query: str, top_k: int = 3) -> list[Document]:
        q_tokens = _content_tokens(query)
        scored: list[tuple[int, int, Document]] = []
        for pos, chunk in enumerate(indexed_chunks):
            overlap = len(q_tokens & _content_tokens(chunk.page_content))
            if overlap > 0:
                scored.append((overlap, -pos, chunk))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [chunk for _ov, _pos, chunk in scored[: max(1, top_k)]]

    return _retrieve


def run_offline_agent_smoke(
    dataset_path: Path = DEFAULT_SQL_DATASET,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
) -> dict[str, Any]:
    """Execute the full offline Agent + Excel SQL plumbing check without network calls."""
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases", [])

    eval_cases: list[AgentEvalCase] = []
    observations: list[AgentTurnObservation] = []

    with tempfile.TemporaryDirectory(prefix="rag_eval_parquet_") as tmp_dir:
        parquet_root = Path(tmp_dir)
        repo, corpus_texts, _parquet_map = _build_offline_eval_fixture(
            corpus_dir,
            raw_cases,
            parquet_root,
        )

        def _load_local_parquet(parquet_key: str) -> bytes:
            return (parquet_root / parquet_key).read_bytes()

        executor = DuckDBSqlExecutor(
            storage_backend="local",
            local_parquet_loader=_load_local_parquet,
            memory_limit="256MB",
            threads=2,
            timeout_seconds=10.0,
            max_rows=200,
        )
        sql_service = ExcelSqlService(repository=repo, executor=executor)
        allowed_views = tuple(b.view_name for b in sql_service.list_authorized_tables(tenant_id="default"))
        queries = DocumentQueries(repo)  # type: ignore[arg-type]
        rag_search_fn = _make_offline_rag_search_fn(corpus_texts)

        with (
            patch.object(settings, "storage_backend", "local"),
            patch.object(settings, "excel_parquet_ingestion_enabled", True),
        ):
            for raw in raw_cases:
                eval_case = AgentEvalCase(
                    case_id=raw["id"],
                    question=raw["question"],
                    expected_route=raw.get("expected_route", "AGENTIC"),
                    expected_tools=tuple(raw.get("expected_tools", [])),
                    expected_facts=tuple(raw.get("expected_facts", [])),
                    expect_sql=bool(raw.get("expect_sql", False)),
                    ground_truth=raw.get("ground_truth", ""),
                )
                eval_cases.append(eval_case)

                scripted_model = _ScriptedOfflineAgentModel(raw)
                orchestrator = ChatOrchestrator(
                    llm=scripted_model,
                    queries=queries,
                    tools_enabled=True,
                    agentic_mode=True,
                    excel_sql_enabled=True,
                    sql_service=sql_service,
                    rag_search_fn=rag_search_fn,
                    tenant_id="default",
                )

                async def _run_turn() -> tuple[str, dict[str, Any]]:
                    plan = await orchestrator.prepare_plan(raw["question"])
                    result = await orchestrator.generate_json(plan)
                    return plan.route, result

                t0 = time.perf_counter()
                actual_route, turn_result = _drive_pure_async_coro(_run_turn())
                elapsed_ms = (time.perf_counter() - t0) * 1000.0

                usage = turn_result.get("usage") or {}
                sources = turn_result.get("sources") or []
                answer_text = str(turn_result.get("answer", ""))
                needs_sources = any(t in ("run_sql", "rag_search") for t in scripted_model.called_tools)
                citations_ok = (len(sources) > 0 and "[1]" in answer_text) if needs_sources else True

                observations.append(
                    AgentTurnObservation(
                        case_id=raw["id"],
                        actual_route=actual_route,
                        called_tools=tuple(scripted_model.called_tools),
                        generated_sql=tuple(scripted_model.generated_sql),
                        allowed_views=allowed_views,
                        answer=answer_text,
                        citations_valid=citations_ok,
                        agent_steps=scripted_model.step_calls,
                        latency_ms=elapsed_ms,
                        ttft_ms=round(elapsed_ms * 0.4, 3),
                        prompt_tokens=int(usage.get("input_tokens", 0)),
                        completion_tokens=int(usage.get("output_tokens", 0)),
                    )
                )

    report = evaluate_agent_trajectory(
        eval_cases,
        observations,
        run_mode="offline_smoke",
    )
    return report.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Agent & Excel SQL Trajectory Evaluation (offline_smoke or live_eval)."
    )
    parser.add_argument(
        "--mode",
        choices=("offline_smoke", "live_eval"),
        default="offline_smoke",
        help="Execution mode. offline_smoke validates plumbing only; live_eval requires isolated eval collection.",
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_SQL_DATASET)
    parser.add_argument("--qdrant-collection", type=str, default="rag_documents_eval")
    parser.add_argument("--approve-live", action="store_true", help="Explicit user approval gate for live_eval.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if args.mode == "offline_smoke":
        report_dict = run_offline_agent_smoke(dataset_path=args.dataset)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report_dict, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[{report_dict['banner']}]")
        print(json.dumps(report_dict["summary"], indent=2, ensure_ascii=False))
        return

    safe_collection = validate_live_eval_collection(args.qdrant_collection)
    if not args.approve_live:
        raise SystemExit(
            f"BLOCKED: --mode live_eval targeting '{safe_collection}' requires explicit --approve-live "
            "after reviewing provider call estimates."
        )
    raise SystemExit(
        f"Live evaluation should be invoked via `python -m evaluation.runner.benchmark_matrix --live "
        f"--approve-live --qdrant-collection {safe_collection}` so Config C runs with full isolated corpus indexing."
    )


if __name__ == "__main__":
    main()
