"""Endpoint chat: gọi RAG pipeline và trả answer + sources."""

import asyncio

from concurrent.futures import CancelledError as FutureCancelledError
from time import monotonic
from typing import Any
from uuid import UUID

from anyio import from_thread
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from app.documents.attachments import AttachmentUnavailableError, resolve_attachments
from app.documents.repository import MongoDocumentRepository, RepositoryError
from fastapi.responses import JSONResponse, StreamingResponse

from app.chat.citation_mapping import map_verified_citations
from app.chat.orchestrator import ChatOrchestrationError, ChatOrchestrator, PreparedChatAnswer
from app.shared.config import settings
from app.conversations.models import new_uuid
from app.conversations.repository import (
    ConversationRepositoryError,
    SessionConflictError,
    SessionDeletedError,
    SessionNotFoundError,
)
from app.conversations.service import (
    ConversationGenerationError,
    ConversationService,
    StreamingTurn,
    create_conversation_service,
)
from app.documents.queries import DocumentQueries
from app.chat.pipeline import (
    PreparedRagStream,
    answer_question,
    astream_rag_answer,
    prepare_rag_stream,
)
from app.api.schemas.chat_documents import (
    ChatError,
    ChatRequest,
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
from app.api.streaming.stream_metrics import StreamMetricTracker, record_stream_metric

router = APIRouter(tags=["chat"])


def _finish_stream_metric(
    tracker: StreamMetricTracker,
    *,
    request_id: str,
    persistent: bool,
    outcome: str,
) -> None:
    metric = tracker.finish(
        request_id=request_id,
        mode="PERSISTENT" if persistent else "STATELESS",
        outcome=outcome,
    )
    if metric is None:
        return
    try:
        record_stream_metric(metric)
    except Exception:  # noqa: BLE001 - observability must never break the response
        pass


def _failed_generation_response(
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
            mode=(
                ChatResponseMode.PERSISTENT
                if persistent
                else ChatResponseMode.STATELESS
            ),
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


async def _encode_provider_stream_impl(
    *,
    request_id: str,
    prepared: PreparedRagStream | PreparedChatAnswer,
    state: dict,
    tracker: StreamMetricTracker,
    service: ConversationService | None = None,
    turn: StreamingTurn | None = None,
    orchestrator: ChatOrchestrator | None = None,
):
    """Encode provider deltas and keep an optional persistent turn truthful."""
    persistent = turn is not None
    sources = [Source(**source) for source in prepared.sources]
    sequence = 1
    tracker.mark_first_event()
    yield encode_sse_event(
        SSEStartEvent(
            data=SSEStartData(
                sequence=sequence,
                request_id=request_id,
                session_id=None if turn is None else turn.user_message.session_id,
                user_message_id=None if turn is None else turn.user_message.message_id,
                assistant_message_id=(
                    None if turn is None else turn.assistant_message.message_id
                ),
                mode=(
                    ChatResponseMode.PERSISTENT
                    if persistent
                    else ChatResponseMode.STATELESS
                ),
            )
        )
    )
    sequence += 1
    yield encode_sse_event(
        SSEMetadataEvent(
            data=SSEMetadataData(
                sequence=sequence,
                model=settings.llm_model,
                sources=sources,
            )
        )
    )

    # Citations need answer ordinals. The contract requires them before the
    # first delta, so P4-02 leaves them absent rather than buffering the full
    # provider answer; durable reconciliation belongs to the lifecycle task.
    usage = None
    emitted_delta = False
    content_parts: list[str] = state["content_parts"]
    error_code = None
    provider_iterator = (
        astream_rag_answer(prepared)
        if orchestrator is None
        else orchestrator.stream_final(prepared)
    ).__aiter__()
    try:
        deadline = asyncio.get_running_loop().time() + settings.stream_timeout_seconds
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if orchestrator is not None and prepared.deadline is not None:
                # Preparation and durable setup share the facade's original budget.
                remaining = min(remaining, prepared.deadline - monotonic())
            if remaining <= 0:
                raise asyncio.TimeoutError
            try:
                chunk = await asyncio.wait_for(
                    provider_iterator.__anext__(), timeout=remaining
                )
            except StopAsyncIteration:
                break
            if chunk.usage is not None:
                usage = chunk.usage
                state["usage"] = usage
            if chunk.content is None:
                continue
            content_parts.append(chunk.content)
            sequence += 1
            emitted_delta = True
            tracker.mark_content()
            yield encode_sse_event(
                SSEDeltaEvent(
                    data=SSEDeltaData(sequence=sequence, content=chunk.content)
                )
            )
        if not emitted_delta:
            error_code = "RAG_STREAM_EMPTY"
    except asyncio.TimeoutError:
        error_code = "RAG_STREAM_TIMEOUT"
        if orchestrator is not None:
            usage = prepared.usage
            state["usage"] = usage
    except ChatOrchestrationError as exc:
        error_code = "RAG_STREAM_ERROR"
        if orchestrator is not None:
            # The facade reports actual aggregate usage, or None for incomplete coverage.
            usage = exc.usage
            state["usage"] = usage
            error_code = {
                "CHAT_TIMEOUT": "RAG_STREAM_TIMEOUT",
                "TOOL_TIMEOUT": "RAG_STREAM_TIMEOUT",
                "CHAT_EMPTY_ANSWER": "RAG_STREAM_EMPTY",
            }.get(exc.code, "RAG_STREAM_ERROR")
    except Exception:  # noqa: BLE001 - never persist a false COMPLETED state
        error_code = "RAG_STREAM_ERROR"
    finally:
        close = getattr(provider_iterator, "aclose", None)
        if close is not None:
            try:
                await asyncio.shield(close())
            except (asyncio.CancelledError, Exception):
                pass

    content = "".join(content_parts)
    # Terminal states follow MessageRecord's existing meaningful-content rule;
    # retain every emitted whitespace character in the wire and stored content.
    if error_code is None and not content.strip():
        error_code = "RAG_STREAM_EMPTY"
    if turn is not None and service is not None:
        try:
            await run_in_threadpool(
                service.finalize_streaming_turn,
                turn,
                content=content,
                sources=prepared.sources,
                usage=usage,
                error_code=error_code,
            )
        except Exception:  # noqa: BLE001 - headers are already sent
            error_code = "STREAM_PERSISTENCE_ERROR"
        finally:
            state["finalized"] = True
    sequence += 1
    _finish_stream_metric(
        tracker,
        request_id=request_id,
        persistent=persistent,
        outcome="COMPLETED" if error_code is None else error_code,
    )
    if error_code is None:
        yield encode_sse_event(
            SSEDoneEvent(data=SSEDoneData(sequence=sequence, usage=usage))
        )
    else:
        yield encode_sse_event(
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


async def _encode_provider_stream(
    *,
    request_id: str,
    prepared: PreparedRagStream | PreparedChatAnswer,
    tracker: StreamMetricTracker | None = None,
    service: ConversationService | None = None,
    turn: StreamingTurn | None = None,
    orchestrator: ChatOrchestrator | None = None,
):
    """Guard the complete response, including disconnects at prefix/delta yields."""
    tracker = tracker or StreamMetricTracker()
    state = {"content_parts": [], "usage": None, "finalized": False}
    stream = _encode_provider_stream_impl(
        request_id=request_id,
        prepared=prepared,
        state=state,
        tracker=tracker,
        service=service,
        turn=turn,
        orchestrator=orchestrator,
    )
    try:
        async for frame in stream:
            yield frame
    except (asyncio.CancelledError, GeneratorExit):
        try:
            await asyncio.shield(stream.aclose())
        except (asyncio.CancelledError, Exception):
            pass
        if turn is not None and service is not None and not state["finalized"]:
            cleanup = asyncio.create_task(
                run_in_threadpool(
                    service.finalize_streaming_turn,
                    turn,
                    content="".join(state["content_parts"]),
                    sources=prepared.sources,
                    usage=state["usage"],
                    error_code="RAG_STREAM_CANCELLED",
                )
            )
            try:
                await asyncio.shield(cleanup)
            except (asyncio.CancelledError, Exception):
                pass
        _finish_stream_metric(
            tracker,
            request_id=request_id,
            persistent=turn is not None,
            outcome="RAG_STREAM_CANCELLED",
        )
        raise
    except Exception:
        _finish_stream_metric(
            tracker,
            request_id=request_id,
            persistent=turn is not None,
            outcome="STREAM_INTERNAL_ERROR",
        )
        raise


async def _attachments(payload, database):
    if not payload.attachments:
        return []
    if database is None:
        raise HTTPException(status_code=503, detail="Document metadata unavailable")
    try:
        return await run_in_threadpool(resolve_attachments, MongoDocumentRepository(database), payload.attachments)
    except AttachmentUnavailableError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(status_code=503, detail="Document metadata unavailable") from exc


async def _answer_with_tools(
    question: str,
    database: Any,
    qdrant_client: Any,
    session_id: str | None = None,
) -> dict:
    """Compose JSON-only dependencies from managed handles, without new clients."""
    queries = DocumentQueries(MongoDocumentRepository(database))
    orchestrator = ChatOrchestrator(queries=queries, tools_enabled=True)
    plan = await orchestrator.prepare_plan(
        question, database=database, qdrant_client=qdrant_client, session_id=session_id,
    )
    return await orchestrator.generate_json(plan)


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={502: {"model": ChatResponse, "description": "Generation failed"}},
)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse | JSONResponse:
    """Trả lời câu hỏi bằng RAG pipeline (retrieve top-k -> prompt -> LLM)."""
    persistent = payload.session_id is not None
    request_id = new_uuid()
    tools_enabled = settings.tool_use_enabled
    try:
        cloud = request.app.state.cloud_connections
        attachments = await _attachments(payload, cloud.mongodb.database)
        if cloud.mongodb.database is None or (not tools_enabled and cloud.qdrant.client is None):
            raise HTTPException(status_code=503, detail="Cloud dependencies chưa sẵn sàng.")
        if not persistent:
            if tools_enabled:
                result = await _answer_with_tools(
                    payload.question, cloud.mongodb.database, cloud.qdrant.client,
                )
            else:
                result = await run_in_threadpool(
                    answer_question,
                    payload.question,
                    database=cloud.mongodb.database,
                    qdrant_client=cloud.qdrant.client,
                )
        else:
            service = await run_in_threadpool(
                create_conversation_service, cloud.mongodb.database
            )

            def generate() -> dict:
                if tools_enabled:
                    # ConversationService owns this worker callback after guard/pair setup.
                    # Return to the request loop instead of creating another SDK event loop.
                    try:
                        return from_thread.run(
                            _answer_with_tools, payload.question, cloud.mongodb.database,
                            cloud.qdrant.client, str(payload.session_id),
                        )
                    except FutureCancelledError:
                        # AnyIO translates async cancellation at the worker bridge.
                        # Preserve ConversationService's dedicated cancellation path.
                        raise asyncio.CancelledError from None
                return answer_question(
                    payload.question,
                    database=cloud.mongodb.database,
                    qdrant_client=cloud.qdrant.client,
                    session_id=str(payload.session_id),
                )

            result = await run_in_threadpool(
                service.answer_with_persistence,
                session_id=str(payload.session_id),
                question=payload.question,
                generate=generate,
                model=settings.llm_model,
                **({"attachments": attachments} if attachments else {}),
            )
    except HTTPException:
        raise
    except SessionDeletedError as exc:
        raise HTTPException(status_code=410, detail="Session đã bị xóa.") from exc
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session không tồn tại.") from exc
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail="Session đang có xung đột trạng thái.") from exc
    except ConversationRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Message persistence tạm thời không khả dụng.") from exc
    except ConversationGenerationError as exc:
        return _failed_generation_response(
            request_id=exc.request_id,
            persistent=True,
            session_id=payload.session_id,
            user_message_id=exc.user_message_id,
            assistant_message_id=exc.assistant_message_id,
            error_code=exc.error_code,
        )
    except ChatOrchestrationError:
        # Real persistent generation is wrapped by ConversationService with durable IDs.
        # Keep the existing public error contract instead of exposing internal tool codes.
        if persistent:
            raise HTTPException(status_code=502, detail="Không thể tạo câu trả lời.") from None
        return _failed_generation_response(request_id=request_id, persistent=False)
    except Exception as exc:  # noqa: BLE001 - chuyển lỗi integration thành lỗi API rõ ràng
        if persistent:
            raise HTTPException(
                status_code=502,
                detail=f"Lỗi RAG pipeline: {type(exc).__name__}",
            ) from exc
        return _failed_generation_response(request_id=request_id, persistent=False)

    return ChatResponse(
        request_id=result.get("request_id") or request_id,
        session_id=payload.session_id,
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
            mode=(
                ChatResponseMode.PERSISTENT
                if persistent
                else ChatResponseMode.STATELESS
            ),
            model=settings.llm_model,
        ),
        usage=result.get("usage"),
        status=ChatResponseStatus.COMPLETED,
        error=None,
    )


@router.post(
    "/chat/stream",
    response_model=None,
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                }
            },
            "description": "Typed SSE transcript",
        },
        502: {"model": ChatResponse, "description": "Generation failed before stream"},
    },
)
async def chat_stream(
    payload: ChatRequest, request: Request
) -> StreamingResponse | JSONResponse:
    """P4-04 SSE endpoint with bounded provider execution and safe termination."""
    persistent = payload.session_id is not None
    request_id = new_uuid()
    tracker = StreamMetricTracker()
    service = None
    turn = None
    tools_enabled = settings.tool_use_enabled
    orchestrator = None
    try:
        cloud = request.app.state.cloud_connections
        attachments = await _attachments(payload, cloud.mongodb.database)
        if cloud.mongodb.database is None or (not tools_enabled and cloud.qdrant.client is None):
            raise HTTPException(status_code=503, detail="Cloud dependencies chưa sẵn sàng.")
        if tools_enabled:
            queries = DocumentQueries(MongoDocumentRepository(cloud.mongodb.database))
            orchestrator = ChatOrchestrator(queries=queries, tools_enabled=True)
            # C05 pre-guard preparation is intentionally retained. No tools run here.
            prepared = await orchestrator.prepare_plan(
                payload.question,
                database=cloud.mongodb.database,
                qdrant_client=cloud.qdrant.client,
                session_id=(None if payload.session_id is None else str(payload.session_id)),
            )
        else:
            prepared = await run_in_threadpool(
                prepare_rag_stream,
                payload.question,
                database=cloud.mongodb.database,
                qdrant_client=cloud.qdrant.client,
                session_id=(None if payload.session_id is None else str(payload.session_id)),
            )
        if persistent:
            service = await run_in_threadpool(
                create_conversation_service, cloud.mongodb.database
            )
            turn = await run_in_threadpool(
                service.begin_streaming_turn,
                session_id=str(payload.session_id),
                question=payload.question,
                model=settings.llm_model,
                **({"attachments": attachments} if attachments else {}),
            )
            request_id = turn.request_id
    except HTTPException as exc:
        _finish_stream_metric(
            tracker,
            request_id=request_id,
            persistent=persistent,
            outcome=f"HTTP_{exc.status_code}",
        )
        raise
    except SessionDeletedError as exc:
        _finish_stream_metric(tracker, request_id=request_id, persistent=True, outcome="HTTP_410")
        raise HTTPException(status_code=410, detail="Session is deleted.") from exc
    except SessionNotFoundError as exc:
        _finish_stream_metric(tracker, request_id=request_id, persistent=True, outcome="HTTP_404")
        raise HTTPException(status_code=404, detail="Session not found.") from exc
    except SessionConflictError as exc:
        _finish_stream_metric(tracker, request_id=request_id, persistent=True, outcome="HTTP_409")
        raise HTTPException(status_code=409, detail="Session generation conflict.") from exc
    except ConversationRepositoryError as exc:
        _finish_stream_metric(tracker, request_id=request_id, persistent=persistent, outcome="HTTP_503")
        raise HTTPException(status_code=503, detail="Message persistence unavailable.") from exc
    except Exception:  # noqa: BLE001 - preserve a safe pre-header error contract
        _finish_stream_metric(
            tracker,
            request_id=request_id,
            persistent=persistent,
            outcome="HTTP_502",
        )
        if persistent:
            raise HTTPException(status_code=502, detail="Unable to initialize answer stream.")
        return _failed_generation_response(request_id=request_id, persistent=False)

    return StreamingResponse(
        _encode_provider_stream(
            request_id=request_id,
            prepared=prepared,
            tracker=tracker,
            service=service,
            turn=turn,
            orchestrator=orchestrator,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
