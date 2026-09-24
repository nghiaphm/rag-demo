"""Script test Phase 2: chunks -> embedding API -> PostgreSQL + pgvector.

Chạy từ project root:
    python backend/scripts/try_vectorstore.py [duong_dan_file]
    python backend/scripts/try_vectorstore.py --fake

Mặc định dùng embedding API (Google Gemini) theo `settings`.
`--fake` dùng `DeterministicFakeEmbedding` của langchain-core để kiểm tra riêng
phần vector store khi chưa có API key; khi đó dùng table riêng có hậu tố `_fake`.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import text

from app.config import settings
from app.db import get_sync_engine
from app.rag.embeddings import get_embeddings
from app.rag.loader import load_document
from app.rag.splitter import split_documents
from app.rag.vectorstore import add_document, get_vectorstore, table_name_for_embedding_model

SAMPLE_FILE = PROJECT_ROOT / "data" / "documents" / "sample_rag.md"
FAKE_EMBEDDING_SIZE = 768
SAMPLE_CONTENT = (
    "Retrieval-Augmented Generation (RAG) kết hợp truy hồi tài liệu với mô hình "
    "ngôn ngữ lớn. Hệ thống tìm các đoạn tài liệu liên quan tới câu hỏi rồi đưa "
    "chúng vào prompt để sinh câu trả lời có căn cứ. "
) * 30


def _ensure_sample_file() -> Path:
    SAMPLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SAMPLE_FILE.exists():
        SAMPLE_FILE.write_text(SAMPLE_CONTENT, encoding="utf-8")
    return SAMPLE_FILE


def _count_rows(table_name: str) -> int:
    with get_sync_engine().connect() as connection:
        result = connection.execute(text(f'SELECT count(*) FROM "{table_name}"'))
        return int(result.scalar_one())


def main() -> None:
    """Load + split file, lưu vào pgvector và xác nhận dữ liệu tồn tại."""
    positional = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    use_fake = "--fake" in sys.argv[1:]

    file_path = Path(positional[0]) if positional else _ensure_sample_file()
    if not file_path.is_file():
        raise SystemExit(f"Không tìm thấy file: {file_path}")

    if use_fake:
        from langchain_core.embeddings import DeterministicFakeEmbedding

        embeddings = DeterministicFakeEmbedding(size=FAKE_EMBEDDING_SIZE)
        print("Embedding          : fake (DeterministicFakeEmbedding, offline)")
    else:
        embeddings = get_embeddings()
        print(f"Embedding provider : {settings.embedding_provider}")
        print(f"Embedding model    : {settings.embedding_model}")

    table_name = table_name_for_embedding_model(settings.embedding_model)
    if use_fake:
        table_name = f"{table_name}_fake"

    documents = load_document(file_path)
    chunks = split_documents(documents)
    document_id = add_document(
        chunks,
        document_id="sample-doc",
        embeddings=embeddings,
        table_name=table_name,
    )

    print(f"Table              : {table_name}")
    print(f"Số chunk đã lưu    : {len(chunks)}")
    print(f"document_id        : {document_id}")
    print(f"Số row trong table : {_count_rows(table_name)}")

    store = get_vectorstore(embeddings=embeddings, table_name=table_name)
    matches = store.similarity_search(chunks[0].page_content, k=1)
    top = matches[0].metadata if matches else {}
    print(
        f"Query store (top-1): {len(matches)} kết quả; "
        f"document_id={top.get('document_id')} chunk_index={top.get('chunk_index')}"
    )


if __name__ == "__main__":
    main()
