"""MongoDB persistence cho session APIs và paginated message history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.conversations.indexes import MESSAGES_COLLECTION, SESSIONS_COLLECTION
from app.conversations.models import MessageRecord, SessionRecord, utc_now


class ConversationRepositoryError(Exception):
    """Persistence error an toàn, không làm lộ MongoDB details."""


class SessionConflictError(ConversationRepositoryError):
    pass


class SessionGenerationConflictError(SessionConflictError):
    pass


class SessionNotFoundError(ConversationRepositoryError):
    pass


class SessionDeletedError(ConversationRepositoryError):
    pass


@dataclass(frozen=True)
class SessionDeleteResult:
    session: SessionRecord
    deleted_messages: int
    already_deleted: bool


class MongoConversationRepository:
    def __init__(self, database: Any):
        if database is None:
            raise ConversationRepositoryError("MongoDB chưa kết nối")
        self.sessions = database[SESSIONS_COLLECTION]
        self.messages = database[MESSAGES_COLLECTION]

    def create_session(self, session: SessionRecord) -> SessionRecord:
        try:
            self.sessions.insert_one(session.to_mongo())
        except DuplicateKeyError as exc:
            raise SessionConflictError("Session đã tồn tại") from exc
        except PyMongoError as exc:
            raise ConversationRepositoryError("Không thể tạo session") from exc
        return session

    def list_sessions(
        self, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[SessionRecord], int]:
        query = {"deleted_at": None}
        try:
            total = self.sessions.count_documents(query)
            values = (
                self.sessions.find(query)
                .sort([("updated_at", DESCENDING), ("_id", DESCENDING)])
                .skip(offset)
                .limit(limit)
            )
            return [SessionRecord.model_validate(value) for value in values], total
        except PyMongoError as exc:
            raise ConversationRepositoryError("Không thể liệt kê sessions") from exc

    def get_session(self, session_id: str, *, include_deleted: bool = False) -> SessionRecord:
        try:
            value = self.sessions.find_one({"_id": session_id})
        except PyMongoError as exc:
            raise ConversationRepositoryError("Không thể đọc session") from exc
        if value is None:
            raise SessionNotFoundError("Session không tồn tại")
        session = SessionRecord.model_validate(value)
        if session.deleted_at is not None and not include_deleted:
            raise SessionDeletedError("Session đã bị xóa")
        return session

    def update_title(self, session_id: str, title: str) -> SessionRecord:
        try:
            value = self.sessions.find_one_and_update(
                {"_id": session_id, "deleted_at": None},
                {"$set": {"title": title, "updated_at": utc_now()}},
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            raise ConversationRepositoryError("Không thể cập nhật session") from exc
        if value is None:
            self.get_session(session_id)
            raise SessionConflictError("Session không thể cập nhật")
        return SessionRecord.model_validate(value)

    def list_messages(
        self, session_id: str, *, offset: int = 0, limit: int = 100
    ) -> tuple[list[MessageRecord], int]:
        self.get_session(session_id)
        query = {"session_id": session_id}
        try:
            total = self.messages.count_documents(query)
            values = (
                self.messages.find(query)
                .sort([("sequence", ASCENDING), ("_id", ASCENDING)])
                .skip(offset)
                .limit(limit)
            )
            return [MessageRecord.model_validate(value) for value in values], total
        except PyMongoError as exc:
            raise ConversationRepositoryError("Không thể đọc message history") from exc

    def begin_generation(self, session_id: str, request_id: str) -> tuple[int, int]:
        """Atomically nhận generation guard và cấp hai sequence liên tiếp."""
        now = utc_now()
        try:
            previous = self.sessions.find_one_and_update(
                {
                    "_id": session_id,
                    "deleted_at": None,
                    "active_generation_id": None,
                },
                {
                    "$inc": {"next_message_sequence": 2},
                    "$set": {
                        "active_generation_id": request_id,
                        "active_generation_started_at": now,
                        "updated_at": now,
                    },
                },
                return_document=ReturnDocument.BEFORE,
            )
        except PyMongoError as exc:
            raise ConversationRepositoryError("Không thể nhận generation guard") from exc
        if previous is None:
            current = self.get_session(session_id)
            if current.active_generation_id is not None:
                raise SessionGenerationConflictError(
                    "Session đã có assistant generation đang hoạt động"
                )
            raise SessionConflictError("Session không thể nhận message")
        first = int(previous.get("next_message_sequence", 1))
        return first, first + 1

    def release_generation(self, session_id: str, request_id: str) -> None:
        """Chỉ owner request hiện tại mới được release guard."""
        now = utc_now()
        try:
            result = self.sessions.update_one(
                {"_id": session_id, "active_generation_id": request_id},
                {
                    "$set": {
                        "active_generation_id": None,
                        "updated_at": now,
                    },
                    "$unset": {"active_generation_started_at": ""},
                },
            )
        except PyMongoError as exc:
            raise ConversationRepositoryError("Không thể release generation guard") from exc
        if result.matched_count != 1:
            raise SessionConflictError("Generation guard không còn thuộc request")

    def create_message_pair(
        self, user_message: MessageRecord, assistant_message: MessageRecord
    ) -> None:
        """Ghi user + assistant placeholder trước generation hoặc không ghi gì."""
        message_ids = [user_message.message_id, assistant_message.message_id]
        try:
            self.messages.insert_many(
                [user_message.to_mongo(), assistant_message.to_mongo()], ordered=True
            )
        except (DuplicateKeyError, PyMongoError) as exc:
            try:
                self.messages.delete_many({"_id": {"$in": message_ids}})
            except PyMongoError:
                pass
            if isinstance(exc, DuplicateKeyError):
                raise SessionConflictError("Message sequence đã tồn tại") from exc
            raise ConversationRepositoryError("Không thể tạo message pair") from exc

    def mark_assistant_streaming(self, message: MessageRecord) -> MessageRecord:
        """Move a durable assistant placeholder into its active stream state."""
        try:
            result = self.messages.replace_one(
                {
                    "_id": message.message_id,
                    "session_id": message.session_id,
                    "request_id": message.request_id,
                    "status": "PENDING",
                },
                message.to_mongo(),
            )
        except PyMongoError as exc:
            raise ConversationRepositoryError("Unable to start assistant stream") from exc
        if result.matched_count != 1:
            raise SessionConflictError("Assistant message is no longer PENDING")
        return message

    def finalize_assistant_message(self, message: MessageRecord) -> MessageRecord:
        """Finalize an owned PENDING/STREAMING assistant message exactly once."""
        try:
            result = self.messages.replace_one(
                {
                    "_id": message.message_id,
                    "session_id": message.session_id,
                    "request_id": message.request_id,
                    "status": {"$in": ["PENDING", "STREAMING"]},
                },
                message.to_mongo(),
            )
        except PyMongoError as exc:
            raise ConversationRepositoryError("Không thể hoàn tất assistant message") from exc
        if result.matched_count != 1:
            raise SessionConflictError("Assistant message không còn ở trạng thái PENDING")
        return message

    def delete_session(self, session_id: str) -> SessionDeleteResult:
        """Soft-delete session trước, sau đó hard-delete toàn bộ messages liên quan."""
        current = self.get_session(session_id, include_deleted=True)
        already_deleted = current.deleted_at is not None
        if not already_deleted and current.active_generation_id is not None:
            raise SessionGenerationConflictError(
                "Không thể xóa session khi generation đang hoạt động"
            )
        try:
            if not already_deleted:
                now = utc_now()
                value = self.sessions.find_one_and_update(
                    {
                        "_id": session_id,
                        "deleted_at": None,
                        "active_generation_id": None,
                    },
                    {"$set": {"deleted_at": now, "updated_at": now}},
                    return_document=ReturnDocument.AFTER,
                )
                if value is None:
                    value = self.sessions.find_one({"_id": session_id})
                    latest = SessionRecord.model_validate(value)
                    if latest.active_generation_id is not None:
                        raise SessionGenerationConflictError(
                            "Không thể xóa session khi generation đang hoạt động"
                        )
                    if latest.deleted_at is None:
                        raise SessionConflictError("Session không thể xóa")
                    already_deleted = latest.deleted_at is not None
                current = SessionRecord.model_validate(value)
            deleted_messages = self.messages.delete_many(
                {"session_id": session_id}
            ).deleted_count
        except PyMongoError as exc:
            raise ConversationRepositoryError("Không thể xóa session") from exc
        return SessionDeleteResult(current, deleted_messages, already_deleted)
