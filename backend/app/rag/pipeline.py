"""Qdrant-backed stateless RAG question-answering use case."""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document

from app.rag.chain import build_rag_chain
from app.rag.retriever import get_retriever


def answer_question(question: str, *, database: Any, qdrant_client: Any) -> dict:
    """Retrieve active MongoDB versions from Qdrant, then generate an answer."""
    retriever = get_retriever(database=database, qdrant_client=qdrant_client)
    result = build_rag_chain(retriever=retriever).invoke(question)
    return {
        "answer": result["answer"],
        "sources": [_to_source(document) for document in result["documents"]],
    }


def _to_source(document: Document) -> dict:
    metadata = document.metadata
    return {
        "file_name": metadata.get("file_name"),
        "source": metadata.get("source"),
        "document_id": metadata.get("document_id"),
        "version_id": metadata.get("version_id"),
        "chunk_id": metadata.get("chunk_id"),
        "chunk_index": metadata.get("chunk_index"),
        "page": metadata.get("page"),
    }
