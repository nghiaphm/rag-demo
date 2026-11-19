"""Public request/response schemas cho Session APIs."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.conversations.models import (
    MessageRole,
    MessageStatus,
    SessionScopeMode,
    SessionSurface,
)
from app.documents.models import _canonical_uuid
from app.documents.attachment_models import MessageAttachment


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    surface: SessionSurface | None = Field(
        default=None,
        description="Bề mặt tạo phiên (workspace hoặc hr); mặc định workspace",
    )

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("title không được rỗng")
        return normalized


class UpdateSessionTitleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title không được rỗng")
        return normalized


class SessionScopeResponse(BaseModel):
    mode: SessionScopeMode
    document_ids: list[str]


class UpdateSessionScopeRequest(BaseModel):
    mode: SessionScopeMode
    document_ids: list[str] = Field(default_factory=list)

    @field_validator("document_ids")
    @classmethod
    def _validate_document_ids(cls, values: list[str]) -> list[str]:
        normalized = [_canonical_uuid(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("document_ids không được trùng")
        return normalized

    @model_validator(mode="after")
    def _validate_mode(self) -> "UpdateSessionScopeRequest":
        if self.mode is SessionScopeMode.ALL_ACTIVE and self.document_ids:
            raise ValueError("ALL_ACTIVE không nhận document_ids")
        if self.mode is SessionScopeMode.SELECTED_DOCUMENTS and not self.document_ids:
            raise ValueError("SELECTED_DOCUMENTS cần ít nhất một document_id")
        return self


class SessionResponse(BaseModel):
    session_id: str
    title: str
    surface: SessionSurface = SessionSurface.WORKSPACE
    scope: SessionScopeResponse
    user_id: str | None
    created_at: datetime
    updated_at: datetime


class SessionPageResponse(BaseModel):
    items: list[SessionResponse]
    offset: int
    limit: int
    total: int


class CitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    version_id: str
    file_name: str | None = None
    page: int | None = None


class UsageResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class MessageResponse(BaseModel):
    attachments: list[MessageAttachment] = Field(default_factory=list)
    message_id: str
    session_id: str
    sequence: int
    role: MessageRole
    content: str
    status: MessageStatus
    citations: list[CitationResponse]
    model: str | None
    usage: UsageResponse | None
    request_id: str
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class MessagePageResponse(BaseModel):
    items: list[MessageResponse]
    offset: int
    limit: int
    total: int


class DeleteSessionResponse(BaseModel):
    session_id: str
    status: str = "DELETED"
    deleted_messages: int
    already_deleted: bool
    message_policy: str = "hard_deleted"
    tombstone_retained: bool = True
    deleted_at: datetime
