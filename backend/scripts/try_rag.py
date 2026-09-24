"""Script test Phase 3: question -> retrieve top-k -> prompt -> LLM -> answer + sources.

Chạy từ project root (cần OPENROUTER_API_KEY hợp lệ và dữ liệu đã index ở Phase 2):
    python backend/scripts/try_rag.py "câu hỏi của bạn"

Không truyền câu hỏi thì script dùng câu hỏi mẫu.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings
from app.rag.chain import build_rag_chain
from app.rag.retriever import get_retriever

DEFAULT_QUESTION = "Tài liệu nói gì về chunk_size và chunk_overlap?"


def main() -> None:
    """Chạy RAG chain với câu hỏi truyền vào (hoặc câu hỏi mặc định)."""
    question = " ".join(sys.argv[1:]).strip() or DEFAULT_QUESTION

    retriever = get_retriever()
    documents = retriever.invoke(question)
    print(f"Provider/model : {settings.embedding_provider} / {settings.embedding_model}")
    print(f"LLM model      : {settings.llm_model}")
    print(f"top_k          : {settings.top_k} (retriever trả {len(documents)} chunk)")

    result = build_rag_chain(retriever=retriever).invoke(question)
    print(f"\nCÂU HỎI: {result['question']}")
    print(f"TRẢ LỜI: {result['answer']}")
    print("\nNGUỒN:")
    for index, document in enumerate(result["documents"], start=1):
        metadata = document.metadata
        print(
            f"  [{index}] {metadata.get('file_name')} | "
            f"page={metadata.get('page')} | chunk_index={metadata.get('chunk_index')}"
        )


if __name__ == "__main__":
    main()
