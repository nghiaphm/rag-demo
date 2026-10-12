"""Application service cho session CRUD và history pagination."""

from dataclasses import dataclass
import asyncio
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.conversation_models import (
    MessageCitation,
    MessageRecord,
    MessageRole,
    MessageStatus,
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
                completed = MessageRecord(
                    message_id=assistant_message.message_id,
                    session_id=session_id,
                    sequence=assistant_sequence,
                    role=MessageRole.ASSISTANT,
                    content=str(result["answer"]),
                    status=MessageStatus.COMPLETED,
                    citations=self._citations_from_sources(result.get("sources", [])),
                    model=model,
                    usage=None,
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
            except Exception:
                self.repository.finalize_assistant_message(
                    self._failed_message(
                        assistant_message, error_code="RAG_PIPELINE_ERROR"
                    )
                )
                raise
            self.repository.finalize_assistant_message(completed)
            return result
        finally:
            self.repository.release_generation(session_id, request_id)

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

    @staticmethod
    def _citations_from_sources(sources: list[dict]) -> list[MessageCitation]:
        citations: list[MessageCitation] = []
        seen_chunk_ids: set[str] = set()
        for source in sources:
            try:
                citation = MessageCitation(
                    chunk_id=source.get("chunk_id"),
                    document_id=source.get("document_id"),
                    version_id=source.get("version_id"),
                    file_name=source.get("file_name"),
                    page=source.get("page"),
                )
            except (ValidationError, TypeError, ValueError):
                continue
            if citation.chunk_id not in seen_chunk_ids:
                citations.append(citation)
                seen_chunk_ids.add(citation.chunk_id)
        return citations


def create_conversation_service(database: Any) -> ConversationService:
    return ConversationService(MongoConversationRepository(database))
