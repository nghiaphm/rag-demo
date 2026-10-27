"""Public request/response schemas cho Session APIs."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.conversation_models import MessageRole, MessageStatus, SessionScopeMode
from app.attachment_models import MessageAttachment


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)

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


class SessionResponse(BaseModel):
    session_id: str
    title: str
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
