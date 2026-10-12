"""Application service cho session CRUD và history pagination."""

from dataclasses import dataclass
import asyncio
from collections.abc import Callable
from typing import Any

from app.citation_mapping import map_verified_citations
from app.conversation_models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
    MessageUsage,
    SessionRecord,
    new_uuid,
    utc_now,
)
from app.conversation_repository import (
    MongoConversationRepository,
    SessionDeleteResult,
)


@dataclass(frozen=True)
class SessionPage:
    items: list[SessionRecord]
    offset: int
    limit: int
    total: int


@dataclass(frozen=True)
class MessagePage:
    items: list[MessageRecord]
    offset: int
    limit: int
    total: int


@dataclass(frozen=True)
class StreamingTurn:
    """Durable IDs and records owned by one persistent SSE generation."""

    request_id: str
    user_message: MessageRecord
    assistant_message: MessageRecord


class ConversationGenerationError(Exception):
    """Safe transport error carrying IDs for an already-created failed turn."""

    def __init__(
        self,
        *,
        request_id: str,
        user_message_id: str,
        assistant_message_id: str,
        error_code: str = "RAG_PIPELINE_ERROR",
    ) -> None:
        super().__init__("Không thể tạo câu trả lời.")
        self.request_id = request_id
        self.user_message_id = user_message_id
        self.assistant_message_id = assistant_message_id
        self.error_code = error_code


class ConversationService:
    def __init__(self, repository: MongoConversationRepository):
        self.repository = repository

    def create_session(self, *, title: str | None = None) -> SessionRecord:
        values = {} if title is None else {"title": title}
        return self.repository.create_session(SessionRecord(**values))

    def list_sessions(self, *, offset: int = 0, limit: int = 50) -> SessionPage:
        items, total = self.repository.list_sessions(offset=offset, limit=limit)
        return SessionPage(items, offset, limit, total)

    def get_session(self, session_id: str) -> SessionRecord:
        return self.repository.get_session(session_id)

    def update_title(self, session_id: str, *, title: str) -> SessionRecord:
        return self.repository.update_title(session_id, title)

    def list_messages(
        self, session_id: str, *, offset: int = 0, limit: int = 100
    ) -> MessagePage:
        items, total = self.repository.list_messages(
            session_id, offset=offset, limit=limit
        )
        return MessagePage(items, offset, limit, total)

    def delete_session(self, session_id: str) -> SessionDeleteResult:
        return self.repository.delete_session(session_id)

    def answer_with_persistence(
        self,
        *,
        session_id: str,
        question: str,
        generate: Callable[[], dict],
        model: str,
    ) -> dict:
        """Persist một non-streaming turn; generation chỉ chạy sau durable placeholders."""
        request_id = new_uuid()
        user_sequence, assistant_sequence = self.repository.begin_generation(
            session_id, request_id
        )
        try:
            user_message = MessageRecord(
                session_id=session_id,
                sequence=user_sequence,
                role=MessageRole.USER,
                content=question,
                status=MessageStatus.COMPLETED,
                request_id=request_id,
            )
            assistant_message = MessageRecord(
                session_id=session_id,
                sequence=assistant_sequence,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.PENDING,
                model=model,
                request_id=request_id,
            )
            self.repository.create_message_pair(user_message, assistant_message)

            try:
                result = generate()
                now = utc_now()
                raw_usage = result.get("usage")
                usage = (
                    None
                    if raw_usage is None
                    else MessageUsage.model_validate(raw_usage)
                )
                completed = MessageRecord(
                    message_id=assistant_message.message_id,
                    session_id=session_id,
                    sequence=assistant_sequence,
                    role=MessageRole.ASSISTANT,
                    content=str(result["answer"]),
                    status=MessageStatus.COMPLETED,
                    citations=map_verified_citations(
                        str(result["answer"]), list(result.get("sources", []))
                    ),
                    model=model,
                    usage=usage,
                    request_id=request_id,
                    created_at=assistant_message.created_at,
                    updated_at=now,
                    completed_at=now,
                )
            except asyncio.CancelledError:
                self.repository.finalize_assistant_message(
                    self._failed_message(
                        assistant_message, error_code="GENERATION_CANCELLED"
                    )
                )
                raise
            except Exception as exc:
                self.repository.finalize_assistant_message(
                    self._failed_message(
                        assistant_message, error_code="RAG_PIPELINE_ERROR"
                    )
                )
                raise ConversationGenerationError(
                    request_id=request_id,
                    user_message_id=user_message.message_id,
                    assistant_message_id=assistant_message.message_id,
                ) from exc
            self.repository.finalize_assistant_message(completed)
            return {
                "answer": completed.content,
                "sources": list(result.get("sources", [])),
                "citations": [item.model_dump() for item in completed.citations],
                "usage": None if usage is None else usage.model_dump(),
                "request_id": request_id,
                "user_message_id": user_message.message_id,
                "assistant_message_id": assistant_message.message_id,
            }
        finally:
            self.repository.release_generation(session_id, request_id)

    def begin_streaming_turn(
        self, *, session_id: str, question: str, model: str
    ) -> StreamingTurn:
        """Persist the user turn and assistant STREAMING state before SSE headers."""
        request_id = new_uuid()
        user_sequence, assistant_sequence = self.repository.begin_generation(
            session_id, request_id
        )
        try:
            user_message = MessageRecord(
                session_id=session_id,
                sequence=user_sequence,
                role=MessageRole.USER,
                content=question,
                status=MessageStatus.COMPLETED,
                request_id=request_id,
            )
            pending = MessageRecord(
                session_id=session_id,
                sequence=assistant_sequence,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.PENDING,
                model=model,
                request_id=request_id,
            )
            self.repository.create_message_pair(user_message, pending)
            streaming = MessageRecord(
                **{
                    **pending.model_dump(),
                    "status": MessageStatus.STREAMING,
                    "updated_at": utc_now(),
                }
            )
            self.repository.mark_assistant_streaming(streaming)
            return StreamingTurn(
                request_id=request_id,
                user_message=user_message,
                assistant_message=streaming,
            )
        except Exception:
            self.repository.release_generation(session_id, request_id)
            raise

    def finalize_streaming_turn(
        self,
        turn: StreamingTurn,
        *,
        content: str,
        sources: list[dict],
        usage: dict | None,
        error_code: str | None = None,
    ) -> MessageRecord:
        """Persist a truthful terminal state and release the session guard."""
        try:
            now = utc_now()
            normalized_content = content.strip()
            if error_code is None:
                status = MessageStatus.COMPLETED
            elif normalized_content:
                status = MessageStatus.PARTIAL
            else:
                status = MessageStatus.FAILED
            normalized_usage = (
                None if usage is None else MessageUsage.model_validate(usage)
            )
            terminal = MessageRecord(
                message_id=turn.assistant_message.message_id,
                session_id=turn.assistant_message.session_id,
                sequence=turn.assistant_message.sequence,
                role=MessageRole.ASSISTANT,
                content=content,
                status=status,
                citations=(
                    []
                    if status is MessageStatus.FAILED
                    else map_verified_citations(content, sources)
                ),
                model=turn.assistant_message.model,
                usage=normalized_usage,
                request_id=turn.request_id,
                error_code=error_code,
                created_at=turn.assistant_message.created_at,
                updated_at=now,
                completed_at=now,
            )
            return self.repository.finalize_assistant_message(terminal)
        finally:
            self.repository.release_generation(
                turn.assistant_message.session_id, turn.request_id
            )

    @staticmethod
    def _failed_message(
        assistant_message: MessageRecord, *, error_code: str
    ) -> MessageRecord:
        now = utc_now()
        return MessageRecord(
            message_id=assistant_message.message_id,
            session_id=assistant_message.session_id,
            sequence=assistant_message.sequence,
            role=MessageRole.ASSISTANT,
            status=MessageStatus.FAILED,
            model=assistant_message.model,
            request_id=assistant_message.request_id,
            error_code=error_code,
            created_at=assistant_message.created_at,
            updated_at=now,
            completed_at=now,
        )

def create_conversation_service(database: Any) -> ConversationService:
    return ConversationService(MongoConversationRepository(database))
