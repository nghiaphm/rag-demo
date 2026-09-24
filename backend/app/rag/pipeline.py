"""Use-case RAG hoàn chỉnh: index document, answer question và quản lý document.

Ghép các component đã hoàn thành ở Phase 1–3 (loader, splitter, vectorstore,
retriever, prompt, llm, chain). Không lưu chat history; không reranker,
hybrid search hay query rewriting.
"""

import uuid
from pathlib import Path

from langchain_core.documents import Document

from app.rag.chain import build_rag_chain
from app.rag.loader import load_document
from app.rag.retriever import get_retriever
from app.rag.splitter import split_documents
from app.rag.vectorstore import add_document, delete_document as delete_chunks
from app.rag.vectorstore import list_documents as list_chunk_documents


def index_document(
    file_path: str | Path,
    *,
    document_id: str | None = None,
    table_name: str | None = None,
) -> dict:
    """Index một file: load -> split -> embedding -> lưu PostgreSQL/pgvector.

    Xóa chunk cũ của cùng `document_id` trước khi add để re-index không để lại
    chunk dư (trường hợp số chunk giảm).

    Args:
        file_path: Đường dẫn file cần index (PDF/Markdown/TXT).
        document_id: ID document; nếu None sẽ sinh UUID mới.
        table_name: Table vector; mặc định suy ra từ `settings.embedding_model`.

    Returns:
        dict gồm `document_id`, `file_name`, `num_chunks`.
    """
    path = Path(file_path)
    resolved_document_id = document_id or str(uuid.uuid4())

    documents = load_document(path)
    chunks = split_documents(documents)

    delete_chunks(resolved_document_id, table_name=table_name)
    add_document(chunks, document_id=resolved_document_id, table_name=table_name)

    return {
        "document_id": resolved_document_id,
        "file_name": path.name,
        "num_chunks": len(chunks),
    }


def answer_question(question: str, *, table_name: str | None = None) -> dict:
    """Trả lời câu hỏi bằng RAG: retrieve top-k -> prompt -> LLM.

    Args:
        question: Câu hỏi của người dùng.
        table_name: Table vector; mặc định suy ra từ `settings.embedding_model`.

    Returns:
        dict gồm `answer` (str) và `sources` (list metadata của các chunk đã retrieve).
    """
    retriever = get_retriever(table_name=table_name)
    result = build_rag_chain(retriever=retriever).invoke(question)
    sources = [_to_source(document) for document in result["documents"]]
    return {"answer": result["answer"], "sources": sources}


def list_documents(*, table_name: str | None = None) -> list[dict]:
    """Liệt kê document đã index kèm số chunk."""
    return list_chunk_documents(table_name=table_name)


def delete_document(document_id: str, *, table_name: str | None = None) -> int:
    """Xóa toàn bộ chunk của một document; trả về số chunk đã xóa."""
    return delete_chunks(document_id, table_name=table_name)


def _to_source(document: Document) -> dict:
    """Trích source metadata tối thiểu của một retrieved Document."""
    metadata = document.metadata
    return {
        "file_name": metadata.get("file_name"),
        "source": metadata.get("source"),
        "document_id": metadata.get("document_id"),
        "chunk_index": metadata.get("chunk_index"),
        "page": metadata.get("page"),
    }
