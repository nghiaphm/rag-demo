"""Shared history-aware RAG preparation for JSON and SSE transports."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompt_values import PromptValue

from app.shared.config import settings
from app.chat.context_budget import (
    BudgetedContext,
    ContextBudgetBuilder,
    ContextBudgetConfig,
)
from app.conversations.models import SessionScope, SessionScopeMode
from app.conversations.repository import MongoConversationRepository
from app.documents.models import DocumentStatus
from app.documents.repository import (
    MongoDocumentRepository,
    RepositoryNotFoundError,
)
from app.conversations.history import ConversationHistoryLoader, HistoryTurn
from app.chat.events import ProviderStreamChunk
from app.chat.query_rewriting import (
    QueryRewriteResult,
    create_query_rewriter,
)
from app.rag.llm import get_llm
from app.rag.prompt import (
    SYSTEM_INSTRUCTION,
    format_context_blocks,
    format_history,
    get_history_aware_rag_prompt,
)
from app.rag.retriever import get_retriever
from app.rag.reranker import get_reranker


@dataclass(frozen=True)
class PreparedRagStream:
    """One immutable RAG request shared by non-stream and stream generation."""

    prompt_value: PromptValue
    sources: list[dict]
    original_query: str = ""
    retrieval_query: str = ""
    history_turns: tuple[HistoryTurn, ...] = ()
    active_version_ids: tuple[str, ...] = ()
    budget: BudgetedContext | None = None
    rewrite: QueryRewriteResult | None = None


async def prepare_rag_request(
    question: str,
    *,
    database: Any,
    qdrant_client: Any,
    session_id: str | None = None,
    reranker: Any | None = None,
) -> PreparedRagStream:
    """Load history/scope, rewrite retrieval query, retrieve and budget one prompt."""
    document_repository = MongoDocumentRepository(database)
    history_turns: tuple[HistoryTurn, ...] = ()
    scope = SessionScope()
    if session_id is not None:
        conversation_repository = MongoConversationRepository(database)
        loaded = await asyncio.to_thread(
            ConversationHistoryLoader(conversation_repository).load,
            session_id,
        )
        history_turns = loaded.turns
        scope = loaded.scope

    active_version_ids = await asyncio.to_thread(
        _resolve_active_version_ids,
        document_repository,
        scope,
    )
    retriever = get_retriever(
        qdrant_client=qdrant_client,
        active_version_ids=active_version_ids,
    )
    return await prepare_rag_request_from_components(
        question,
        history_turns=history_turns,
        active_version_ids=active_version_ids,
        retriever=retriever,
        reranker=reranker,
    )


async def prepare_rag_request_from_components(
    question: str,
    *,
    history_turns: tuple[HistoryTurn, ...],
    active_version_ids: tuple[str, ...],
    retriever: Any,
    query_rewriter: Any | None = None,
    budget_builder: ContextBudgetBuilder | None = None,
    reranker: Any | None = None,
) -> PreparedRagStream:
    """Pure integration seam shared by production and isolated evaluation."""
    resolved_budget_builder = budget_builder or ContextBudgetBuilder(
        ContextBudgetConfig.from_settings(settings)
    )
    history_budget = resolved_budget_builder.build(
        system=SYSTEM_INSTRUCTION,
        history_turns=history_turns,
        chunks=(),
        query=question,
    )
    rewriter = query_rewriter or create_query_rewriter(settings)
    rewrite = await rewriter.rewrite(
        question, history_budget.history_turns
    )
    raw_documents = await asyncio.to_thread(retriever.invoke, rewrite.retrieval_query)
    resolved_reranker = reranker if reranker is not None else get_reranker()
    documents = await asyncio.to_thread(
        resolved_reranker.rerank,
        rewrite.retrieval_query,
        raw_documents,
        top_k=settings.top_k,
        relevance_threshold=settings.reranker_relevance_threshold,
    )
    budget = resolved_budget_builder.build(
        system=SYSTEM_INSTRUCTION,
        history_turns=history_turns,
        chunks=format_context_blocks(documents),
        query=question,
    )
    selected_documents = documents[: len(budget.chunks)]
    context = (
        "\n\n".join(budget.chunks)
        if budget.chunks
        else "(không có tài liệu liên quan)"
    )
    prompt_value = get_history_aware_rag_prompt().invoke(
        {
            "history": format_history(budget.history_turns),
            "context": context,
            # Generation always receives the original (possibly budget-truncated)
            # query, never the rewritten retrieval query.
            "question": budget.query,
        }
    )
    return PreparedRagStream(
        prompt_value=prompt_value,
        sources=[_to_source(document) for document in selected_documents],
        original_query=question,
        retrieval_query=rewrite.retrieval_query,
        history_turns=budget.history_turns,
        active_version_ids=active_version_ids,
        budget=budget,
        rewrite=rewrite,
    )


async def answer_question_async(
    question: str,
    *,
    database: Any,
    qdrant_client: Any,
    session_id: str | None = None,
) -> dict:
    """Prepare through the shared builder and generate one non-stream response."""
    prepared = await prepare_rag_request(
        question,
        database=database,
        qdrant_client=qdrant_client,
        session_id=session_id,
    )
    return await generate_prepared_answer(prepared)


async def generate_prepared_answer(
    prepared: PreparedRagStream,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Generate a non-stream result from the exact prompt shared with SSE."""
    response = await (llm or get_llm()).ainvoke(prepared.prompt_value)
    answer = _text_delta(response)
    if answer is None or not answer.strip():
        raise ValueError("LLM không trả nội dung")
    return {
        "answer": answer,
        "sources": prepared.sources,
        "usage": _usage_from_chunk(response),
    }


def answer_question(
    question: str,
    *,
    database: Any,
    qdrant_client: Any,
    session_id: str | None = None,
) -> dict:
    """Compatibility wrapper for scripts that still execute the stateless path sync."""
    return asyncio.run(
        answer_question_async(
            question,
            database=database,
            qdrant_client=qdrant_client,
            session_id=session_id,
        )
    )


def prepare_rag_stream(
    question: str,
    *,
    database: Any,
    qdrant_client: Any,
    session_id: str | None = None,
) -> PreparedRagStream:
    """Compatibility wrapper for non-async callers and older smoke tests."""
    return asyncio.run(
        prepare_rag_request(
            question,
            database=database,
            qdrant_client=qdrant_client,
            session_id=session_id,
        )
    )


async def astream_rag_answer(
    prepared: PreparedRagStream,
    *,
    llm: BaseChatModel | None = None,
) -> AsyncIterator[ProviderStreamChunk]:
    """Consume Groq/OpenAI-compatible async chunks and normalize text plus usage."""
    resolved_llm = llm if llm is not None else get_llm()
    async for chunk in resolved_llm.astream(prepared.prompt_value):
        yield ProviderStreamChunk(
            content=_text_delta(chunk),
            usage=_usage_from_chunk(chunk),
        )


def _resolve_active_version_ids(
    repository: MongoDocumentRepository,
    scope: SessionScope,
) -> tuple[str, ...]:
    """Resolve a server-owned session scope to active versions only."""
    if scope.mode is SessionScopeMode.ALL_ACTIVE:
        return tuple(repository.list_active_version_ids())

    version_ids: list[str] = []
    for document_id in scope.document_ids:
        try:
            document = repository.get_document(document_id)
        except RepositoryNotFoundError:
            continue
        if (
            document.status is DocumentStatus.INDEXED
            and document.active_version_id is not None
            and document.deleted_at is None
        ):
            version_ids.append(document.active_version_id)
    return tuple(version_ids)


def _text_delta(chunk: Any) -> str | None:
    """Keep only textual provider content; ignore tool/control/empty chunks."""
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content or None
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    text = "".join(parts)
    return text or None


def _usage_from_chunk(chunk: Any) -> dict[str, int] | None:
    """Normalize LangChain/OpenAI-compatible usage without trusting unknown shapes."""
    candidates = [getattr(chunk, "usage_metadata", None), getattr(chunk, "usage", None)]
    response_metadata = getattr(chunk, "response_metadata", None)
    if isinstance(response_metadata, dict):
        candidates.extend(
            [response_metadata.get("usage"), response_metadata.get("usage_metadata")]
        )
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        input_tokens = raw.get("input_tokens", raw.get("prompt_tokens"))
        output_tokens = raw.get("output_tokens", raw.get("completion_tokens"))
        total_tokens = raw.get("total_tokens")
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            continue
        if input_tokens < 0 or output_tokens < 0:
            continue
        if not isinstance(total_tokens, int):
            total_tokens = input_tokens + output_tokens
        if total_tokens < input_tokens + output_tokens:
            continue
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
    return None


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
        **({"sheet_name": metadata["sheet_name"], "row_index": metadata.get("row_index")} if metadata.get("sheet_name") is not None else {}),
    }
