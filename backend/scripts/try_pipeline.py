"""Script test end-to-end Phase 4: index_document -> answer_question -> sources.

Chạy từ project root (cần OPENROUTER_API_KEY và EMBEDDING_API_KEY hợp lệ):
    python backend/scripts/try_pipeline.py

Fixture (`sample_pipeline.md`) được tạo trong `backend/fixtures/` và index vào
**fixture table riêng** `{table}_fixtures` (không đụng table demo/runtime).
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "fixtures"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings
from app.rag.pipeline import answer_question, index_document
from app.rag.vectorstore import table_name_for_embedding_model

SAMPLE_FILE = FIXTURES_DIR / "sample_pipeline.md"
SAMPLE_DOCUMENT_ID = "sample-pipeline-doc"
FIXTURE_TABLE = f"{table_name_for_embedding_model(settings.embedding_model)}_fixtures"

SAMPLE_CONTENT = """# RAG Demo V1 - Ghi chú kỹ thuật

## Vector database
RAG Demo V1 lưu vector trong PostgreSQL phiên bản 16 kèm phần mở rộng pgvector 0.8.6.
Mỗi embedding model được lưu trong một table riêng, ví dụ rag_chunks_gemini_embedding_001.

## Chunking
Chiến lược chunk mặc định là RecursiveCharacterTextSplitter với chunk_size 500 ký tự
và chunk_overlap 50 ký tự. Cả hai giá trị đều được đọc từ file cấu hình, không hard-code.

## Embedding
Embedding baseline dùng model gemini-embedding-001 do Google cung cấp qua API (free tier).
Vector của model này có 3072 chiều. Khi đổi embedding model thì phải re-index toàn bộ dữ liệu.

## LLM
LLM baseline được gọi qua OpenRouter và có thể đổi model bằng biến cấu hình LLM_MODEL
mà không cần sửa pipeline chính.

## Cost control
Dự án ưu tiên model free hoặc free tier ở baseline để giữ chi phí gần 0 trong giai đoạn test.
"""

QUESTIONS_IN_DOCUMENT = [
    "Chunk size và chunk overlap mặc định là bao nhiêu?",
    "Hệ thống dùng vector database nào?",
]
QUESTION_OUT_OF_DOCUMENT = "Giá cổ phiếu của Vinamilk hôm nay là bao nhiêu?"


def _ensure_sample_file() -> Path:
    """Tạo fixture trong `backend/fixtures/` nếu chưa tồn tại."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    if not SAMPLE_FILE.exists():
        SAMPLE_FILE.write_text(SAMPLE_CONTENT, encoding="utf-8")
    return SAMPLE_FILE


def _print_sources(sources: list[dict]) -> None:
    for index, source in enumerate(sources, start=1):
        print(
            f"  [{index}] file_name={source.get('file_name')} | source={source.get('source')} "
            f"| document_id={source.get('document_id')} | chunk_index={source.get('chunk_index')} "
            f"| page={source.get('page')}"
        )


def main() -> None:
    """Index fixture rồi chạy các câu hỏi in-document và out-of-document trên fixture table."""
    print(f"Embedding : {settings.embedding_provider} / {settings.embedding_model}")
    print(f"LLM       : {settings.llm_model}")
    print(f"top_k     : {settings.top_k}")
    print(f"Table     : {FIXTURE_TABLE}")

    sample_path = _ensure_sample_file()
    index_result = index_document(
        sample_path,
        document_id=SAMPLE_DOCUMENT_ID,
        table_name=FIXTURE_TABLE,
    )
    print("\n[INDEX]")
    print(f"  document_id = {index_result['document_id']}")
    print(f"  file_name   = {index_result['file_name']}")
    print(f"  num_chunks  = {index_result['num_chunks']}")

    for question in QUESTIONS_IN_DOCUMENT:
        result = answer_question(question, table_name=FIXTURE_TABLE)
        print(f"\n[CÂU HỎI - có trong tài liệu] {question}")
        print(f"  ANSWER  : {result['answer']}")
        print(f"  SOURCES : {len(result['sources'])}")
        _print_sources(result["sources"])

    result = answer_question(QUESTION_OUT_OF_DOCUMENT, table_name=FIXTURE_TABLE)
    print(f"\n[CÂU HỎI - không có trong tài liệu] {QUESTION_OUT_OF_DOCUMENT}")
    print(f"  ANSWER  : {result['answer']}")
    print(f"  SOURCES : {len(result['sources'])}")
    _print_sources(result["sources"])


if __name__ == "__main__":
    main()
