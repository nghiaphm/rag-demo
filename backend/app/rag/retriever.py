"""Retriever lấy top-k chunk liên quan từ vector store đã xây ở Phase 2."""

from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever

from app.config import settings
from app.rag.vectorstore import get_vectorstore


def get_retriever(
    embeddings: Embeddings | None = None,
    table_name: str | None = None,
    *,
    top_k: int | None = None,
) -> BaseRetriever:
    """Trả về LangChain retriever dùng similarity search trên pgvector.

    Args:
        embeddings: Embeddings object; mặc định dùng `get_embeddings()`.
        table_name: Tên table vector; mặc định suy ra từ `settings.embedding_model`.
        top_k: Số chunk lấy về; mặc định lấy từ `settings.top_k`.

    Returns:
        `BaseRetriever` với `search_kwargs={"k": top_k}`.
    """
    k = top_k if top_k is not None else settings.top_k
    store = get_vectorstore(embeddings=embeddings, table_name=table_name)
    return store.as_retriever(search_kwargs={"k": k})
