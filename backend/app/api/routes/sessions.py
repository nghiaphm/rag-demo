"""Session CRUD và paginated message-history APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.api.dependencies.auth import get_current_user
from app.shared.auth import UserContext, can_access_resource

from app.conversations.models import (
    MessageRecord,
    SessionRecord,
    SessionScopeMode,
    SessionSurface,
)
from app.conversations.repository import (
    ConversationRepositoryError,
    SessionConflictError,
    SessionDeletedError,
    SessionNotFoundError,
)
from app.documents.repository import MongoDocumentRepository, RepositoryNotFoundError
from app.api.schemas.conversations import (
    CitationResponse,
    CreateSessionRequest,
    DeleteSessionResponse,
    MessagePageResponse,
    MessageResponse,
    SessionPageResponse,
    SessionResponse,
    SessionScopeResponse,
    UpdateSessionScopeRequest,
    UpdateSessionTitleRequest,
    UsageResponse,
)
from app.conversations.service import ConversationService, create_conversation_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _service(request: Request) -> ConversationService:
    database = request.app.state.cloud_connections.mongodb.database
    if database is None:
        raise HTTPException(status_code=503, detail="Cloud dependencies chưa sẵn sàng.")
    return await run_in_threadpool(create_conversation_service, database)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, SessionDeletedError):
        raise HTTPException(status_code=410, detail="Session đã bị xóa.") from exc
    if isinstance(exc, SessionNotFoundError):
        raise HTTPException(status_code=404, detail="Session không tồn tại.") from exc
    if isinstance(exc, SessionConflictError):
        raise HTTPException(status_code=409, detail="Session đang có xung đột trạng thái.") from exc
    if isinstance(exc, ConversationRepositoryError):
        raise HTTPException(status_code=503, detail="Session metadata tạm thời không khả dụng.") from exc
    raise exc


def _session_response(session: SessionRecord) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        title=session.title,
        surface=session.surface,
        scope=SessionScopeResponse(
            mode=session.scope.mode,
            document_ids=session.scope.document_ids,
        ),
        user_id=session.user_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _message_response(message: MessageRecord) -> MessageResponse:
    return MessageResponse(
        message_id=message.message_id,
        session_id=message.session_id,
        sequence=message.sequence,
        role=message.role,
        content=message.content,
        status=message.status,
        citations=[CitationResponse(**item.model_dump()) for item in message.citations],
        attachments=message.attachments,
        model=message.model,
        usage=None if message.usage is None else UsageResponse(**message.usage.model_dump()),
        request_id=message.request_id,
        error_code=message.error_code,
        created_at=message.created_at,
        updated_at=message.updated_at,
        completed_at=message.completed_at,
    )


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    payload: CreateSessionRequest, request: Request
) -> SessionResponse:
    service = await _service(request)
    try:
        session = await run_in_threadpool(
            service.create_session,
            title=payload.title,
            **({"surface": payload.surface} if payload.surface is not None else {}),
        )
    except Exception as exc:
        _handle_error(exc)
    return _session_response(session)


@router.get("", response_model=SessionPageResponse)
async def list_sessions(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    surface: SessionSurface | None = Query(default=None),
) -> SessionPageResponse:
    service = await _service(request)
    try:
        page = await run_in_threadpool(
            service.list_sessions,
            offset=offset,
            limit=limit,
            **({"surface": surface} if surface is not None else {}),
        )
    except Exception as exc:
        _handle_error(exc)
    return SessionPageResponse(
        items=[_session_response(item) for item in page.items],
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    request: Request,
    session_id: UUID,
    current_user: UserContext | None = Depends(get_current_user),
) -> SessionResponse:
    service = await _service(request)
    try:
        session = await run_in_threadpool(service.get_session, str(session_id))
    except Exception as exc:
        _handle_error(exc)
    if not can_access_resource(
        user=current_user,
        owner_id=session.user_id,
        allowed_roles=session.allowed_roles,
    ):
        raise HTTPException(status_code=403, detail="Không có quyền truy cập session này.")
    return _session_response(session)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session_title(
    payload: UpdateSessionTitleRequest,
    request: Request,
    session_id: UUID,
    current_user: UserContext | None = Depends(get_current_user),
) -> SessionResponse:
    service = await _service(request)
    try:
        if current_user is not None:
            existing = await run_in_threadpool(service.get_session, str(session_id))
            if not can_access_resource(
                user=current_user,
                owner_id=existing.user_id,
                allowed_roles=existing.allowed_roles,
            ):
                raise HTTPException(status_code=403, detail="Không có quyền cập nhật session này.")
        session = await run_in_threadpool(
            service.update_title, str(session_id), title=payload.title
        )
    except HTTPException:
        raise
    except Exception as exc:
        _handle_error(exc)
    return _session_response(session)


@router.patch("/{session_id}/scope", response_model=SessionResponse)
async def update_session_scope(
    payload: UpdateSessionScopeRequest,
    request: Request,
    session_id: UUID,
    current_user: UserContext | None = Depends(get_current_user),
) -> SessionResponse:
    """Chuyển đổi phạm vi tài liệu truy vấn của session (ALL_ACTIVE / SELECTED_DOCUMENTS)."""
    service = await _service(request)
    try:
        if current_user is not None:
            existing = await run_in_threadpool(service.get_session, str(session_id))
            if not can_access_resource(
                user=current_user,
                owner_id=existing.user_id,
                allowed_roles=existing.allowed_roles,
            ):
                raise HTTPException(status_code=403, detail="Không có quyền cập nhật phạm vi session này.")
            database = request.app.state.cloud_connections.mongodb.database
            if (
                payload.mode is SessionScopeMode.SELECTED_DOCUMENTS
                and hasattr(database, "__getitem__")
            ):
                doc_repo = MongoDocumentRepository(database)
                for doc_id in payload.document_ids:
                    try:
                        doc = await run_in_threadpool(doc_repo.get_document, doc_id)
                    except RepositoryNotFoundError as exc:
                        raise HTTPException(status_code=404, detail="Tài liệu được chọn không tồn tại.") from exc
                    if doc.deleted_at is not None:
                        raise HTTPException(status_code=404, detail="Tài liệu được chọn đã bị xóa.")
                    if not can_access_resource(
                        user=current_user,
                        owner_id=doc.owner_id,
                        allowed_roles=doc.allowed_roles,
                    ):
                        raise HTTPException(status_code=403, detail="Không có quyền chọn tài liệu ngoài phân quyền.")
        session = await run_in_threadpool(
            service.update_scope,
            str(session_id),
            mode=payload.mode,
            document_ids=payload.document_ids,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _handle_error(exc)
    return _session_response(session)


@router.get("/{session_id}/messages", response_model=MessagePageResponse)
async def list_session_messages(
    request: Request,
    session_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: UserContext | None = Depends(get_current_user),
) -> MessagePageResponse:
    service = await _service(request)
    try:
        if current_user is not None:
            existing = await run_in_threadpool(service.get_session, str(session_id))
            if not can_access_resource(
                user=current_user,
                owner_id=existing.user_id,
                allowed_roles=existing.allowed_roles,
            ):
                raise HTTPException(status_code=403, detail="Không có quyền đọc session này.")
        page = await run_in_threadpool(
            service.list_messages,
            str(session_id),
            offset=offset,
            limit=limit,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _handle_error(exc)
    return MessagePageResponse(
        items=[_message_response(item) for item in page.items],
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.delete("/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(
    request: Request,
    session_id: UUID,
    current_user: UserContext | None = Depends(get_current_user),
) -> DeleteSessionResponse:
    service = await _service(request)
    try:
        if current_user is not None:
            existing = await run_in_threadpool(service.get_session, str(session_id))
            if not can_access_resource(
                user=current_user,
                owner_id=existing.user_id,
                allowed_roles=existing.allowed_roles,
            ):
                raise HTTPException(status_code=403, detail="Không có quyền xóa session này.")
        result = await run_in_threadpool(service.delete_session, str(session_id))
    except HTTPException:
        raise
    except Exception as exc:
        _handle_error(exc)
    return DeleteSessionResponse(
        session_id=result.session.session_id,
        deleted_messages=result.deleted_messages,
        already_deleted=result.already_deleted,
        deleted_at=result.session.deleted_at,
    )
