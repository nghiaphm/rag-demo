"""CLI đánh giá baseline RAG trên golden set nhỏ.

Chạy từ project root:
    python backend/evaluation/runner/eval_cli.py
    python backend/evaluation/runner/eval_cli.py --no-reindex
    python backend/evaluation/runner/eval_cli.py --out backend/evaluation/results/run.json

Script index corpus trong backend/evaluation/datasets/corpus/ vào một Qdrant collection riêng
(không đụng dữ liệu demo), chạy từng case qua đúng retriever/chain hiện tại,
tính metric deterministic, in kết quả và lưu JSON để so sánh các configuration.
"""

import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.callbacks import BaseCallbackHandler

from app.shared.config import settings
from app.infrastructure.qdrant import QdrantConnection
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.rag.chain import build_rag_chain
from app.rag.embeddings import get_embeddings
from app.rag.loaders.files import load_document
from app.rag.retriever import get_retriever
from app.rag.splitter import split_documents
from app.rag.vector_index import VectorFilter, VectorRecord, chunk_point_id
from evaluation.scoring.metrics import (
    answer_fact_coverage,
    faithfulness_ratio,
    retrieval_metrics,
)

EVAL_DIR = BACKEND_DIR / "evaluation"
DATASET_DIR = EVAL_DIR / "datasets"
CORPUS_DIR = DATASET_DIR / "corpus"
GOLDEN_SET_PATH = DATASET_DIR / "golden_set.json"
RESULTS_DIR = EVAL_DIR / "results"
EVAL_COLLECTION = f"{settings.qdrant_collection[:250]}_eval"
FALLBACK_PHRASE = "Không tìm thấy thông tin trong tài liệu"
FAITHFULNESS_THRESHOLD = 0.7
MAX_ATTEMPTS = 3  # 1 lần gọi + 2 lần thử lại cho lỗi tạm thời của provider


class TokenUsageCallback(BaseCallbackHandler):
    """Thu token usage từ LLM response nếu provider trả metadata."""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.available = False

    def on_llm_end(self, response, **kwargs) -> None:  # type: ignore[override]
        usage = None
        try:
            generation = response.generations[0][0]
            message = getattr(generation, "message", None)
            usage = getattr(message, "usage_metadata", None)
        except (IndexError, AttributeError):
            usage = None

        if not usage and getattr(response, "llm_output", None):
            llm_output = response.llm_output
            usage = llm_output.get("token_usage") or llm_output.get("usage")

        if not usage:
            return

        self.available = True
        self.input_tokens += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        self.output_tokens += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        self.total_tokens += int(usage.get("total_tokens") or 0)


def _corpus_identity(path: Path) -> tuple[str, str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    document_id = str(uuid5(NAMESPACE_URL, f"rag-demo-eval-document:{path.name}"))
    version_id = str(uuid5(NAMESPACE_URL, f"{document_id}:{digest}"))
    return document_id, version_id


def _active_eval_versions() -> tuple[str, ...]:
    return tuple(_corpus_identity(path)[1] for path in sorted(CORPUS_DIR.glob("*.md")))


def _index_corpus(vector_index, embeddings) -> list[dict]:
    """Index lại corpus vào collection eval riêng, idempotent theo document identity."""
    indexed: list[dict] = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        document_id, version_id = _corpus_identity(path)
        chunks = split_documents(load_document(path))
        vectors = embeddings.embed_documents([chunk.page_content for chunk in chunks])
        vector_index.delete(VectorFilter(document_id=document_id))
        vector_index.upsert([
            VectorRecord(
                point_id=chunk_point_id(version_id, chunk_index),
                document_id=document_id,
                version_id=version_id,
                chunk_index=chunk_index,
                file_name=path.name,
                chunk_text=chunk.page_content,
                page=None if chunk.metadata.get("page") is None else int(chunk.metadata["page"]),
                vector=tuple(vector),
            )
            for chunk_index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ])
        count = vector_index.count(VectorFilter(version_id=version_id))
        if count != len(chunks):
            raise RuntimeError("Eval Qdrant chunk count mismatch")
        indexed.append({
            "document_id": document_id,
            "version_id": version_id,
            "file_name": path.name,
            "num_chunks": count,
        })
    return indexed


def _load_golden_set() -> dict:
    return json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))


def _build_case_result(case: dict, result: dict, callback: TokenUsageCallback, latency_ms: float) -> dict:
    """Tính metric cho một case từ output của chain."""
    documents = result["documents"]
    retrieved_sources = [document.metadata.get("file_name") for document in documents]
    context = "\n\n".join(document.page_content for document in documents)
    answer = result["answer"]

    expect_fallback = bool(case.get("expect_fallback", False))
    retrieval = retrieval_metrics(retrieved_sources, case.get("expected_sources", []))
    coverage = None if expect_fallback else answer_fact_coverage(answer, case.get("expected_facts", []))
    faith_ratio = faithfulness_ratio(answer, context)

    if expect_fallback:
        fallback_correct: bool | None = FALLBACK_PHRASE in answer
        faithful = bool(fallback_correct)
    else:
        fallback_correct = None
        faithful = faith_ratio >= FAITHFULNESS_THRESHOLD

    return {
        "id": case["id"],
        "question": case["question"],
        "error": None,
        "top_k": len(documents),
        "retrieved_sources": sorted({source for source in retrieved_sources if source}),
        "retrieval_hit": retrieval["retrieval_hit"],
        "retrieval_recall": retrieval["retrieval_recall"],
        "answer": answer,
        "answer_fact_coverage": coverage,
        "answer_relevant": None if coverage is None else coverage >= 1.0,
        "expect_fallback": expect_fallback,
        "fallback_correct": fallback_correct,
        "faithfulness_ratio": round(faith_ratio, 3),
        "faithful": faithful,
        "latency_ms": round(latency_ms, 1),
        "tokens": {
            "input": callback.input_tokens,
            "output": callback.output_tokens,
            "total": callback.total_tokens,
            "available": callback.available,
        },
    }


def _error_case_result(case: dict, error: Exception) -> dict:
    """Case bị lỗi integration sau khi đã thử lại: ghi nhận, không làm sập cả run."""
    return {
        "id": case["id"],
        "question": case["question"],
        "error": type(error).__name__,
        "top_k": 0,
        "retrieved_sources": [],
        "retrieval_hit": None,
        "retrieval_recall": None,
        "answer": "",
        "answer_fact_coverage": None,
        "answer_relevant": None,
        "expect_fallback": bool(case.get("expect_fallback", False)),
        "fallback_correct": None,
        "faithfulness_ratio": None,
        "faithful": False,
        "latency_ms": None,
        "tokens": {"input": 0, "output": 0, "total": 0, "available": False},
    }


def _run_case(case: dict, chain) -> dict:
    """Chạy một case (có retry cho lỗi tạm thời) và tính metric."""
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        callback = TokenUsageCallback()
        started = time.perf_counter()
        try:
            result = chain.invoke(case["question"], config={"callbacks": [callback]})
        except Exception as exc:  # noqa: BLE001 - lỗi mạng/provider có thể tạm thời
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(2 * (attempt + 1))
            continue
        latency_ms = (time.perf_counter() - started) * 1000
        return _build_case_result(case, result, callback, latency_ms)

    return _error_case_result(case, last_error)  # type: ignore[arg-type]


def _mean(values: list) -> float | None:
    """Trung bình (bỏ qua None); None nếu rỗng."""
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return round(statistics.fmean(cleaned), 3)


def _summarize(cases: list[dict]) -> dict:
    """Tổng hợp metric toàn bộ golden set (bỏ qua case lỗi)."""
    ok_cases = [case for case in cases if not case["error"]]
    errors = [case for case in cases if case["error"]]
    in_doc = [case for case in ok_cases if not case["expect_fallback"]]
    out_doc = [case for case in ok_cases if case["expect_fallback"]]
    latencies = [case["latency_ms"] for case in ok_cases if case["latency_ms"] is not None]
    tokens_available = bool(ok_cases) and all(case["tokens"]["available"] for case in ok_cases)

    return {
        "n_cases": len(cases),
        "n_ok": len(ok_cases),
        "n_errors": len(errors),
        "error_ids": [case["id"] for case in errors],
        "n_in_document": len(in_doc),
        "n_out_of_document": len(out_doc),
        "retrieval_hit_rate": _mean([bool(case["retrieval_hit"]) for case in in_doc]),
        "mean_retrieval_recall": _mean([case["retrieval_recall"] for case in in_doc]),
        "answer_relevance_rate": _mean([bool(case["answer_relevant"]) for case in in_doc]),
        "mean_answer_fact_coverage": _mean([case["answer_fact_coverage"] for case in in_doc]),
        "faithfulness_rate": _mean([bool(case["faithful"]) for case in ok_cases]),
        "fallback_accuracy": _mean([bool(case["fallback_correct"]) for case in out_doc]),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 1) if latencies else None,
            "max": round(max(latencies), 1) if latencies else None,
        },
        "tokens": {
            "available": tokens_available,
            "input": sum(case["tokens"]["input"] for case in ok_cases),
            "output": sum(case["tokens"]["output"] for case in ok_cases),
            "total": sum(case["tokens"]["total"] for case in ok_cases),
        },
    }


def _print_case(case: dict) -> None:
    print(f"\n[{case['id']}] {case['question']}")
    if case["error"]:
        print(f"  ERROR: {case['error']} (đã hết retry)")
        return
    print(f"  retrieved ({case['top_k']}): {case['retrieved_sources']}")
    print(f"  retrieval_hit={case['retrieval_hit']} retrieval_recall={case['retrieval_recall']}")
    print(f"  answer: {case['answer']}")
    if case["expect_fallback"]:
        print(f"  fallback_correct={case['fallback_correct']}")
    else:
        print(f"  fact_coverage={case['answer_fact_coverage']} answer_relevant={case['answer_relevant']}")
    print(
        f"  faithful={case['faithful']} (ratio={case['faithfulness_ratio']}) "
        f"latency={case['latency_ms']}ms tokens={case['tokens']['total']}"
    )


def main() -> None:
    """Index corpus (tùy chọn) và chạy toàn bộ golden set."""
    parser = argparse.ArgumentParser(description="RAG baseline evaluation trên golden set.")
    parser.add_argument("--no-reindex", action="store_true", help="Bỏ qua bước index lại corpus.")
    parser.add_argument("--out", type=Path, default=None, help="Đường dẫn file JSON lưu kết quả.")
    args = parser.parse_args()

    connection = QdrantConnection()
    status = connection.connect()
    if not status.ok or connection.client is None:
        print(f"BLOCKED: qdrant ok={status.ok}; code={status.code}")
        raise SystemExit(2)
    embeddings = get_embeddings()
    vector_index = QdrantVectorIndex(connection.client, EVAL_COLLECTION)
    try:
        golden_set = _load_golden_set()
        indexed = [] if args.no_reindex else _index_corpus(vector_index, embeddings)

        print("Cấu hình:")
        print(f"  LLM               : {settings.llm_model}")
        print(f"  Embedding         : {settings.embedding_provider} / {settings.embedding_model}")
        print(f"  chunk_size/overlap: {settings.chunk_size}/{settings.chunk_overlap} | top_k={settings.top_k}")
        print(f"  eval collection   : {EVAL_COLLECTION}")
        if indexed:
            print(f"  corpus đã index   : {[item['file_name'] for item in indexed]}")

        retriever = get_retriever(
            vector_index=vector_index,
            embeddings=embeddings,
            active_version_ids=_active_eval_versions(),
        )
        chain = build_rag_chain(retriever=retriever)

        cases = [_run_case(case, chain) for case in golden_set["cases"]]
        for case in cases:
            _print_case(case)

        summary = _summarize(cases)
        print("\n===== TỔNG HỢP =====")
        for key, value in summary.items():
            print(f"  {key}: {value}")

        report = {
            "golden_set": golden_set.get("name"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": {
                "llm_model": settings.llm_model,
                "embedding_provider": settings.embedding_provider,
                "embedding_model": settings.embedding_model,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "top_k": settings.top_k,
                "collection": EVAL_COLLECTION,
            },
            "cases": cases,
            "summary": summary,
        }

        out_path = args.out
        if out_path is None:
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_path = RESULTS_DIR / f"eval_{stamp}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nĐã lưu kết quả: {out_path}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
