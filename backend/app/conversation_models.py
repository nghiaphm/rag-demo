"""MongoDB records cho session và message persistence.

P2-01 chỉ định nghĩa persistence contract. API, ghi message trong ``/chat`` và
atomic generation guard được triển khai ở các task sau.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import Field, field_validator, model_validator

from app.document_models import MongoRecord, _canonical_uuid, new_uuid, utc_now
from app.attachment_models import MessageAttachment


class SessionScopeMode(str, Enum):
    """Scope retrieval được lưu cùng session, không nhận ACL tùy ý từ client."""

    ALL_ACTIVE = "ALL_ACTIVE"
    SELECTED_DOCUMENTS = "SELECTED_DOCUMENTS"


class MessageRole(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MessageStatus(str, Enum):
    PENDING = "PENDING"
    STREAMING = "STREAMING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class SessionScope(MongoRecord):
    """Retrieval scope bền vững; mặc định toàn bộ active documents."""

    mode: SessionScopeMode = SessionScopeMode.ALL_ACTIVE
    document_ids: list[str] = Field(default_factory=list)

    @field_validator("document_ids")
    @classmethod
    def _validate_document_ids(cls, values: list[str]) -> list[str]:
        normalized = [_canonical_uuid(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("document_ids không được trùng")
        return normalized

    @model_validator(mode="after")
    def _validate_mode(self) -> "SessionScope":
        if self.mode is SessionScopeMode.ALL_ACTIVE and self.document_ids:
            raise ValueError("ALL_ACTIVE không nhận document_ids")
        if self.mode is SessionScopeMode.SELECTED_DOCUMENTS and not self.document_ids:
            raise ValueError("SELECTED_DOCUMENTS cần ít nhất một document_id")
        return self


class SessionRecord(MongoRecord):
    """Conversation identity và retrieval scope trong collection ``sessions``."""

    session_id: str = Field(default_factory=new_uuid, alias="_id")
    title: str = Field(default="Cuộc trò chuyện mới", min_length=1, max_length=200)
    scope: SessionScope = Field(default_factory=SessionScope)
    user_id: str | None = Field(default=None, min_length=1, max_length=255)
    next_message_sequence: int = Field(default=1, ge=1)
    active_generation_id: str | None = None
    active_generation_started_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    deleted_at: datetime | None = None

    _validate_session_id = field_validator("session_id")(_canonical_uuid)
    _validate_active_generation_id = field_validator("active_generation_id")(
        lambda value: None if value is None else _canonical_uuid(value)
    )

    @field_validator("title", "user_id")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("giá trị không được rỗng")
        return normalized

    @field_validator(
        "created_at", "updated_at", "deleted_at", "active_generation_started_at"
    )
    @classmethod
    def _normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime phải có timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _validate_generation_guard(self) -> "SessionRecord":
        has_id = self.active_generation_id is not None
        has_started_at = self.active_generation_started_at is not None
        if has_id != has_started_at:
            raise ValueError("generation guard cần đồng thời ID và started_at")
        return self


class MessageCitation(MongoRecord):
    """Citation có thể truy ngược chính xác tới chunk/version đã retrieve."""

    chunk_id: str
    document_id: str
    version_id: str
    file_name: str | None = Field(default=None, min_length=1, max_length=255)
    page: int | None = Field(default=None, ge=0)

    _validate_chunk_id = field_validator("chunk_id")(_canonical_uuid)
    _validate_document_id = field_validator("document_id")(_canonical_uuid)
    _validate_version_id = field_validator("version_id")(_canonical_uuid)


class MessageUsage(MongoRecord):
    """Token usage chuẩn hóa khi provider trả về; có thể vắng mặt."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_total(self) -> "MessageUsage":
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens không được nhỏ hơn input + output")
        return self


class MessageRecord(MongoRecord):
    """Một message có ID riêng và sequence đơn điệu trong một session."""

    message_id: str = Field(default_factory=new_uuid, alias="_id")
    session_id: str
    sequence: int = Field(ge=1)
    role: MessageRole
    content: str = Field(default="", max_length=1_000_000)
    status: MessageStatus
    citations: list[MessageCitation] = Field(default_factory=list)
    attachments: list[MessageAttachment] = Field(default_factory=list, max_length=20)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    usage: MessageUsage | None = None
    request_id: str = Field(default_factory=new_uuid)
    error_code: str | None = Field(default=None, min_length=1, max_length=100)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None

    _validate_message_id = field_validator("message_id")(_canonical_uuid)
    _validate_session_id = field_validator("session_id")(_canonical_uuid)
    _validate_request_id = field_validator("request_id")(_canonical_uuid)

    @field_validator("created_at", "updated_at", "completed_at")
    @classmethod
    def _normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime phải có timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _validate_role_and_state(self) -> "MessageRecord":
        if self.role is MessageRole.ASSISTANT and self.attachments:
            raise ValueError("Only user messages can carry attachments")
        if self.role is MessageRole.USER:
            if self.status is not MessageStatus.COMPLETED:
                raise ValueError("user message phải có status COMPLETED")
            if not self.content.strip():
                raise ValueError("user message không được rỗng")
            if self.citations or self.model is not None or self.usage is not None:
                raise ValueError("user message không mang citation/model/usage")
        elif self.status in {MessageStatus.COMPLETED, MessageStatus.PARTIAL} and not self.content.strip():
            raise ValueError("assistant message terminal có nội dung không được rỗng")

        if self.status is MessageStatus.FAILED and not self.error_code:
            raise ValueError("FAILED message cần error_code an toàn")
        if self.status not in {MessageStatus.FAILED, MessageStatus.PARTIAL} and self.error_code is not None:
            raise ValueError("error_code chỉ dùng cho terminal failure message")
        return self
