"""Adapter từ domain/application values của Chat sang wire format (SSE frame hoặc JSON).

Chỉ module trong `app.api.streaming` được biết SSE schema. Chat phát
:class:`app.chat.events.ProviderStreamChunk` và result dict; adapter này dựng frame/response
mà không đổi byte output so với hợp đồng hiện có.
"""

from __future__ import annotations

from uuid import UUID

from fastapi.responses import JSONResponse

from app.api.schemas.chat_documents import (
    ChatError,
    ChatResponse,
    ChatResponseMetadata,
    ChatResponseMode,
    ChatResponseStatus,
    Citation,
    Source,
)
from app.api.streaming.sse_schema import (
    SSEDeltaData,
    SSEDeltaEvent,
    SSEDoneData,
    SSEDoneEvent,
    SSEErrorData,
    SSEErrorEvent,
    SSEMetadataData,
    SSEMetadataEvent,
    SSEStartData,
    SSEStartEvent,
    encode_sse_event,
)
from app.chat.citation_mapping import map_verified_citations
from app.chat.orchestrator import ChatOrchestrationError
from app.conversations.service import StreamingTurn
from app.shared.config import settings

_ORCHESTRATION_STREAM_ERROR_CODES = {
    "CHAT_TIMEOUT": "RAG_STREAM_TIMEOUT",
    "TOOL_TIMEOUT": "RAG_STREAM_TIMEOUT",
    "CHAT_EMPTY_ANSWER": "RAG_STREAM_EMPTY",
}


def _mode(persistent: bool) -> ChatResponseMode:
    return ChatResponseMode.PERSISTENT if persistent else ChatResponseMode.STATELESS


def start_frame(*, sequence: int, request_id: str, turn: StreamingTurn | None) -> str:
    return encode_sse_event(
        SSEStartEvent(
            data=SSEStartData(
                sequence=sequence,
                request_id=request_id,
                session_id=None if turn is None else turn.user_message.session_id,
                user_message_id=None if turn is None else turn.user_message.message_id,
                assistant_message_id=(
                    None if turn is None else turn.assistant_message.message_id
                ),
                mode=_mode(turn is not None),
            )
        )
    )


def metadata_frame(*, sequence: int, sources: list[Source]) -> str:
    return encode_sse_event(
        SSEMetadataEvent(
            data=SSEMetadataData(
                sequence=sequence,
                model=settings.llm_model,
                sources=sources,
            )
        )
    )


def delta_frame(*, sequence: int, content: str) -> str:
    return encode_sse_event(
        SSEDeltaEvent(data=SSEDeltaData(sequence=sequence, content=content))
    )


def done_frame(*, sequence: int, usage: dict | None) -> str:
    return encode_sse_event(SSEDoneEvent(data=SSEDoneData(sequence=sequence, usage=usage)))


def error_frame(*, sequence: int, content: str, error_code: str, usage: dict | None) -> str:
    return encode_sse_event(
        SSEErrorEvent(
            data=SSEErrorData(
                sequence=sequence,
                status="PARTIAL" if content.strip() else "FAILED",
                error=ChatError(
                    code=error_code,
                    message="Luồng tạo câu trả lời không thể hoàn tất.",
                    retryable=True,
                ),
                usage=usage,
            )
        )
    )


def stream_error_code_for_orchestration(exc: ChatOrchestrationError) -> str:
    """Map internal orchestration codes to the public SSE error vocabulary."""
    return _ORCHESTRATION_STREAM_ERROR_CODES.get(exc.code, "RAG_STREAM_ERROR")


def failed_generation_response(
    *,
    request_id: str,
    persistent: bool,
    session_id: str | UUID | None = None,
    user_message_id: str | UUID | None = None,
    assistant_message_id: str | UUID | None = None,
    error_code: str = "RAG_PIPELINE_ERROR",
) -> JSONResponse:
    response = ChatResponse(
        request_id=request_id,
        session_id=session_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        answer=None,
        sources=[],
        citations=[],
        metadata=ChatResponseMetadata(
            mode=_mode(persistent),
            model=settings.llm_model,
        ),
        usage=None,
        status=ChatResponseStatus.FAILED,
        error=ChatError(
            code=error_code,
            message="Không thể tạo câu trả lời.",
            retryable=True,
        ),
    )
    return JSONResponse(status_code=502, content=response.model_dump(mode="json"))


def completed_chat_response(
    *,
    result: dict,
    request_id: str,
    session_id: UUID | str | None,
    persistent: bool,
) -> ChatResponse:
    """Collect a finished generation result into the public JSON response."""
    return ChatResponse(
        request_id=result.get("request_id") or request_id,
        session_id=session_id,
        user_message_id=result.get("user_message_id"),
        assistant_message_id=result.get("assistant_message_id"),
        answer=result["answer"],
        sources=[Source(**source) for source in result["sources"]],
        citations=[
            Citation(**citation)
            for citation in map_verified_citations(
                str(result["answer"]), list(result.get("sources", []))
            )
        ],
        metadata=ChatResponseMetadata(
            mode=_mode(persistent),
            model=settings.llm_model,
        ),
        usage=result.get("usage"),
        status=ChatResponseStatus.COMPLETED,
        error=None,
    )
