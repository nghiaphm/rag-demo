"""Endpoint chat: gọi RAG pipeline và trả answer + sources."""

import asyncio

from concurrent.futures import CancelledError as FutureCancelledError
from time import monotonic
from typing import Any
from uuid import UUID

from anyio import from_thread
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from app.api.dependencies.auth import get_current_user
from app.api.dependencies.client_ip import resolve_client_ip
from app.shared.auth import UserContext
from app.shared.observability import get_metrics_recorder, get_request_id
from app.documents.attachments import AttachmentUnavailableError, resolve_attachments
from app.documents.repository import MongoDocumentRepository, RepositoryError
from fastapi.responses import JSONResponse, StreamingResponse

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
from app.chat.ui_context import (
    UiDashboardContractStatus,
    UiDashboardDepartment,
    UiDashboardKnowledgeBase,
    UiDashboardKpi,
    UiDashboardSnapshot,
    UiPageContext,
    UiRelatedPage,
)
from app.api.schemas.chat_documents import (
    ChatRequest,
    ChatResponse,
    ChatUiContext,
    Source,
)
from app.api.streaming.event_adapter import (
    completed_chat_response,
    delta_frame,
    done_frame,
    error_frame,
    failed_generation_response,
    metadata_frame,
    start_frame,
    stream_error_code_for_orchestration,
)
from app.api.streaming.stream_metrics import StreamMetricTracker, record_stream_metric


router = APIRouter(tags=["chat"])


async def _enforce_rate_limit(request: Request, current_user: UserContext | None) -> None:
    if not settings.rate_limit_enabled:
        return
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    client_host = resolve_client_ip(request, settings.trusted_proxy_ips)
    key = current_user.user_id if current_user is not None else client_host
    allowed = await limiter.allow(key, limit=settings.rate_limit_requests_per_minute, window_seconds=60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Quá giới hạn số lượt yêu cầu. Vui lòng thử lại sau.")


def _resolve_turn_uuid() -> str:
    """Reuse context request_id when it is a valid UUID; otherwise mint a turn UUID."""
    ctx_req_id = get_request_id()
    if ctx_req_id:
        try:
            return str(UUID(ctx_req_id))
        except ValueError:
            pass
    return new_uuid()


def _route_type_label(*, tools_enabled: bool, agentic_enabled: bool = False) -> str:
    if tools_enabled and agentic_enabled:
        return "agentic"
    if tools_enabled:
        return "document_tools"
    return "rag"


def _finish_stream_metric(
    tracker: StreamMetricTracker,
    *,
    request_id: str,
    persistent: bool,
    outcome: str,
    route_type: str = "rag",
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
        get_metrics_recorder().record_chat_turn(
            transport="sse",
            mode="persistent" if persistent else "stateless",
            route_type=route_type,
            outcome=outcome,
        )
    except Exception:  # noqa: BLE001 - observability must never break the response
        pass


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
    is_agentic = orchestrator is not None and getattr(prepared, "route", None) == "AGENTIC"
    sequence = 1
    tracker.mark_first_event()
    yield start_frame(sequence=sequence, request_id=request_id, turn=turn)
    metadata_emitted = False
    if not is_agentic:
        sources = [Source(**source) for source in prepared.sources]
        sequence += 1
        metadata_emitted = True
        yield metadata_frame(sequence=sequence, sources=sources)

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
            if not metadata_emitted:
                sources = [Source(**source) for source in prepared.sources]
                sequence += 1
                metadata_emitted = True
                yield metadata_frame(sequence=sequence, sources=sources)
            if chunk.usage is not None:
                usage = chunk.usage
                state["usage"] = usage
            if chunk.content is None:
                continue
            content_parts.append(chunk.content)
            sequence += 1
            emitted_delta = True
            tracker.mark_content()
            yield delta_frame(sequence=sequence, content=chunk.content)
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
            error_code = stream_error_code_for_orchestration(exc)
    except Exception:  # noqa: BLE001 - never persist a false COMPLETED state
        error_code = "RAG_STREAM_ERROR"
    finally:
        close = getattr(provider_iterator, "aclose", None)
        if close is not None:
            try:
                await asyncio.shield(close())
            except (asyncio.CancelledError, Exception):
                pass

    if not metadata_emitted:
        sources = [Source(**source) for source in prepared.sources]
        sequence += 1
        metadata_emitted = True
        yield metadata_frame(sequence=sequence, sources=sources)

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
        yield done_frame(sequence=sequence, usage=usage)
    else:
        yield error_frame(
            sequence=sequence, content=content, error_code=error_code, usage=usage
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


def _to_domain_ui_context(ui_context: ChatUiContext | None) -> UiPageContext | None:
    if ui_context is None:
        return None
    snapshot = None
    if ui_context.dashboard_snapshot is not None:
        raw_snap = ui_context.dashboard_snapshot
        kb = (
            UiDashboardKnowledgeBase(
                total_documents=raw_snap.knowledge_base.total_documents,
                indexed_documents=raw_snap.knowledge_base.indexed_documents,
                processing_documents=raw_snap.knowledge_base.processing_documents,
                failed_documents=raw_snap.knowledge_base.failed_documents,
                total_chunks=raw_snap.knowledge_base.total_chunks,
            )
            if raw_snap.knowledge_base is not None
            else None
        )
        snapshot = UiDashboardSnapshot(
            as_of_label=raw_snap.as_of_label,
            total_employees=raw_snap.total_employees,
            kpis=tuple(
                UiDashboardKpi(
                    label=kpi.label,
                    value=kpi.value,
                    delta_label=kpi.delta_label,
                    trend=kpi.trend,
                    helper_text=kpi.helper_text,
                )
                for kpi in raw_snap.kpis
            ),
            departments=tuple(
                UiDashboardDepartment(
                    department=dept.department,
                    count=dept.count,
                    open_roles=dept.open_roles,
                )
                for dept in raw_snap.departments
            ),
            contract_statuses=tuple(
                UiDashboardContractStatus(
                    label=item.label,
                    count=item.count,
                )
                for item in raw_snap.contract_statuses
            ),
            knowledge_base=kb,
        )
    return UiPageContext(
        portal=ui_context.portal,
        route=ui_context.route,
        page_title=ui_context.page_title,
        page_purpose=ui_context.page_purpose,
        available_features=tuple(ui_context.available_features),
        related_pages=tuple(
            UiRelatedPage(
                route=page.route,
                title=page.title,
                description=page.description,
            )
            for page in ui_context.related_pages
        ),
        selected_document_name=ui_context.selected_document_name,
        selected_category=ui_context.selected_category,
        dashboard_snapshot=snapshot,
    )


def _excel_sql_orchestrator_kwargs(
    request: Request | None,
    current_user: UserContext | None,
) -> dict[str, Any]:
    if not settings.excel_sql_enabled:
        return {}
    sql_service = (
        getattr(request.app.state, "excel_sql_service", None)
        if request is not None
        else None
    )
    tenant_id = (
        current_user.tenant_id
        if current_user is not None and getattr(current_user, "tenant_id", None)
        else settings.default_tenant_id
    )
    return {
        "sql_service": sql_service,
        "current_user": current_user,
        "tenant_id": tenant_id,
    }


async def _answer_with_tools(
    question: str,
    database: Any,
    qdrant_client: Any,
    session_id: str | None = None,
    tracer: Any = None,
    ui_context: UiPageContext | None = None,
    request: Request | None = None,
    current_user: UserContext | None = None,
) -> dict:
    """Compose JSON-only dependencies from managed handles, without new clients."""
    queries = DocumentQueries(MongoDocumentRepository(database))
    orchestrator = ChatOrchestrator(
        queries=queries,
        tools_enabled=True,
        **({"tracer": tracer} if tracer is not None else {}),
        **_excel_sql_orchestrator_kwargs(request, current_user),
    )
    plan = await orchestrator.prepare_plan(
        question,
        database=database,
        qdrant_client=qdrant_client,
        session_id=session_id,
        **({"ui_context": ui_context} if ui_context is not None else {}),
    )
    return await orchestrator.generate_json(plan)


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={502: {"model": ChatResponse, "description": "Generation failed"}},
)
async def chat(
    payload: ChatRequest,
    request: Request,
    current_user: UserContext | None = Depends(get_current_user),
) -> ChatResponse | JSONResponse:
    """Trả lời câu hỏi bằng RAG pipeline (retrieve top-k -> prompt -> LLM)."""
    await _enforce_rate_limit(request, current_user)
    persistent = payload.session_id is not None
    request_id = _resolve_turn_uuid()
    tools_enabled = settings.tool_use_enabled
    route_type = _route_type_label(
        tools_enabled=tools_enabled,
        agentic_enabled=bool(getattr(settings, "agentic_mode_enabled", False)),
    )
    tracer = getattr(request.app.state, "tracer", None)
    domain_ui_context = _to_domain_ui_context(payload.ui_context)
    try:
        cloud = request.app.state.cloud_connections
        attachments = await _attachments(payload, cloud.mongodb.database)
        if cloud.mongodb.database is None or (not tools_enabled and cloud.qdrant.client is None):
            raise HTTPException(status_code=503, detail="Cloud dependencies chưa sẵn sàng.")
        if not persistent:
            if tools_enabled:
                result = await _answer_with_tools(
                    payload.question,
                    cloud.mongodb.database,
                    cloud.qdrant.client,
                    **({"tracer": tracer} if tracer is not None else {}),
                    **({"ui_context": domain_ui_context} if domain_ui_context is not None else {}),
                    **(
                        {"request": request, "current_user": current_user}
                        if settings.excel_sql_enabled
                        else {}
                    ),
                )
            else:
                result = await run_in_threadpool(
                    answer_question,
                    payload.question,
                    database=cloud.mongodb.database,
                    qdrant_client=cloud.qdrant.client,
                    **({"ui_context": domain_ui_context} if domain_ui_context is not None else {}),
                    **({"tracer": tracer} if tracer is not None else {}),
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
                        extra_args = (
                            (request, current_user)
                            if settings.excel_sql_enabled
                            else ()
                        )
                        return from_thread.run(
                            _answer_with_tools, payload.question, cloud.mongodb.database,
                            cloud.qdrant.client, str(payload.session_id),
                            tracer,
                            domain_ui_context,
                            *extra_args,
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
                    **({"ui_context": domain_ui_context} if domain_ui_context is not None else {}),
                    **({"tracer": tracer} if tracer is not None else {}),
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
        return failed_generation_response(
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
        return failed_generation_response(request_id=request_id, persistent=False)
    except Exception as exc:  # noqa: BLE001 - chuyển lỗi integration thành lỗi API rõ ràng
        if persistent:
            raise HTTPException(
                status_code=502,
                detail=f"Lỗi RAG pipeline: {type(exc).__name__}",
            ) from exc
        return failed_generation_response(request_id=request_id, persistent=False)

    get_metrics_recorder().record_chat_turn(
        transport="json",
        mode="persistent" if persistent else "stateless",
        route_type=route_type,
        outcome="COMPLETED",
    )
    return completed_chat_response(
        result=result,
        request_id=request_id,
        session_id=payload.session_id,
        persistent=persistent,
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
    payload: ChatRequest,
    request: Request,
    current_user: UserContext | None = Depends(get_current_user),
) -> StreamingResponse | JSONResponse:
    """P4-04 SSE endpoint with bounded provider execution and safe termination."""
    await _enforce_rate_limit(request, current_user)
    persistent = payload.session_id is not None
    request_id = _resolve_turn_uuid()
    tracker = StreamMetricTracker()
    service = None
    turn = None
    tools_enabled = settings.tool_use_enabled
    orchestrator = None
    tracer = getattr(request.app.state, "tracer", None)
    domain_ui_context = _to_domain_ui_context(payload.ui_context)
    try:
        cloud = request.app.state.cloud_connections
        attachments = await _attachments(payload, cloud.mongodb.database)
        if cloud.mongodb.database is None or (not tools_enabled and cloud.qdrant.client is None):
            raise HTTPException(status_code=503, detail="Cloud dependencies chưa sẵn sàng.")
        if tools_enabled:
            queries = DocumentQueries(MongoDocumentRepository(cloud.mongodb.database))
            orchestrator = ChatOrchestrator(
                queries=queries,
                tools_enabled=True,
                **({"tracer": tracer} if tracer is not None else {}),
                **_excel_sql_orchestrator_kwargs(request, current_user),
            )
            # C05 pre-guard preparation is intentionally retained. No tools run here.
            prepared = await orchestrator.prepare_plan(
                payload.question,
                database=cloud.mongodb.database,
                qdrant_client=cloud.qdrant.client,
                session_id=(None if payload.session_id is None else str(payload.session_id)),
                **({"ui_context": domain_ui_context} if domain_ui_context is not None else {}),
            )
        else:
            prepared = await run_in_threadpool(
                prepare_rag_stream,
                payload.question,
                database=cloud.mongodb.database,
                qdrant_client=cloud.qdrant.client,
                session_id=(None if payload.session_id is None else str(payload.session_id)),
                **({"ui_context": domain_ui_context} if domain_ui_context is not None else {}),
                **({"tracer": tracer} if tracer is not None else {}),
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
        return failed_generation_response(request_id=request_id, persistent=False)

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
