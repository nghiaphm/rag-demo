"""Agentic tool definitions and synchronous handlers (Metadata + Iterative RAG Search)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.documents import Document

from app.documents.queries import DocumentQueries
from app.documents.tool_handlers import create_document_tool_registry, document_tool_definitions
from app.rag.reranker import get_reranker
from app.rag.retriever import get_retriever
from app.shared.config import settings
from app.tool_use.contracts import (
    RagSearchArguments,
    ToolContractError,
    ToolDefinition,
    ToolEnvelope,
    ToolHandler,
    failure_result,
    success_result,
    validate_arguments,
)


def rag_search_tool_definition() -> ToolDefinition:
    """Tool schema allowing the Agent to run targeted RAG searches iteratively."""
    return ToolDefinition(
        name="rag_search",
        description=(
            "Search indexed document chunks for specific facts, policies, metrics, or sections. "
            "Use focused keywords; you may call this multiple times with different queries."
        ),
        arguments_type=RagSearchArguments,
    )


def agent_tool_definitions(*, include_rag_search: bool = True) -> tuple[ToolDefinition, ...]:
    """Return tool definitions exposed to the Agentic Orchestrator."""
    base = tuple(document_tool_definitions())
    if include_rag_search:
        return (*base, rag_search_tool_definition())
    return base


def agent_tool_schemas(*, include_rag_search: bool = True) -> list[dict[str, Any]]:
    """OpenAI-compatible function tool schemas for model.bind_tools()."""
    return [
        {
            "type": "function",
            "function": {
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.input_schema(),
            },
        }
        for definition in agent_tool_definitions(include_rag_search=include_rag_search)
    ]


def _doc_to_source(document: Document) -> dict[str, Any]:
    metadata = document.metadata or {}
    return {
        "chunk_id": metadata.get("chunk_id"),
        "document_id": metadata.get("document_id"),
        "version_id": metadata.get("version_id"),
        "file_name": metadata.get("file_name") or metadata.get("title") or "unknown",
        "page": metadata.get("page"),
        "chunk_index": metadata.get("chunk_index"),
    }


def _append_unique_sources(target: list[dict[str, Any]], docs: list[Document]) -> None:
    seen = {
        (s.get("chunk_id"), s.get("version_id"), s.get("chunk_index"), s.get("file_name"))
        for s in target
    }
    for doc in docs:
        src = _doc_to_source(doc)
        key = (src.get("chunk_id"), src.get("version_id"), src.get("chunk_index"), src.get("file_name"))
        if key not in seen:
            seen.add(key)
            target.append(src)


def create_rag_search_handler(
    *,
    retrieve_fn: Callable[[str, int], list[Document]] | None = None,
    qdrant_client: Any = None,
    active_version_ids: tuple[str, ...] = (),
    collected_sources: list[dict[str, Any]] | None = None,
) -> ToolHandler:
    """Build a synchronous ToolExecutor-compatible rag_search handler."""

    def _rag_search(arguments: object) -> ToolEnvelope:
        try:
            values = validate_arguments("rag_search", arguments)
        except ToolContractError as exc:
            return failure_result("rag_search", exc.code)

        query = str(values["query"])
        top_k = int(values["top_k"])
        try:
            if retrieve_fn is not None:
                docs = list(retrieve_fn(query, top_k))[:top_k]
            else:
                if qdrant_client is None:
                    return failure_result("rag_search", "TOOL_QUERY_FAILED")
                retriever = get_retriever(
                    qdrant_client=qdrant_client,
                    active_version_ids=active_version_ids,
                )
                raw_docs = retriever.invoke(query)
                reranker = get_reranker()
                docs = reranker.rerank(
                    query,
                    raw_docs,
                    top_k=top_k,
                    relevance_threshold=settings.reranker_relevance_threshold,
                )

            if collected_sources is not None:
                _append_unique_sources(collected_sources, docs)

            hits = [
                {
                    "file_name": (doc.metadata or {}).get("file_name") or "unknown",
                    "page": (doc.metadata or {}).get("page"),
                    "chunk_index": (doc.metadata or {}).get("chunk_index"),
                    "snippet": (doc.page_content or "")[:450],
                }
                for doc in docs
            ]
            return success_result(
                "rag_search",
                {"query": query, "count": len(hits), "hits": hits},
            )
        except Exception:
            return failure_result("rag_search", "TOOL_QUERY_FAILED")

    return _rag_search


def create_agent_tool_registry(
    queries: DocumentQueries | None,
    *,
    rag_search_handler: ToolHandler | None = None,
) -> dict[str, ToolHandler]:
    """Assemble combined read-only document + rag_search registry for AgenticRunner."""
    registry: dict[str, ToolHandler] = {}
    if queries is not None:
        registry.update(create_document_tool_registry(queries))
    if rag_search_handler is not None:
        registry["rag_search"] = rag_search_handler
    return registry
