"""Pydantic schemas cho request/response của FastAPI."""

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.documents.models import DocumentStatus
from app.documents.attachment_models import AttachmentReference


class WorkbookSheetPreview(BaseModel):
    name: str
    columns: list[str]
    rows: list[list[str]]
    total_rows: int
    truncated: bool


class DocumentPreviewResponse(BaseModel):
    document_id: str
    version_id: str
    file_name: str
    kind: Literal["text", "excel", "unsupported"]
    text: str | None = None
    sheets: list[WorkbookSheetPreview] = Field(default_factory=list)
    truncated: bool = False


class Source(BaseModel):
    """Metadata nguồn của một chunk được retrieve."""

    file_name: str | None = None
    source: str | None = None
    document_id: str | None = None
    version_id: str | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None
    page: int | None = None
    sheet_name: str | None = None
    row_index: int | None = None


class Citation(BaseModel):
    """Citation truy ngược được; mapping eligibility được hoàn thiện ở P3-02."""

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    file_name: str | None = None
    page: int | None = Field(default=None, ge=0)


class ChatResponseStatus(str, Enum):
    """Terminal status của logical non-streaming reply."""

    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ChatResponseMode(str, Enum):
    STATELESS = "STATELESS"
    PERSISTENT = "PERSISTENT"


class ChatResponseMetadata(BaseModel):
    """Provider-neutral metadata; object này luôn hiện diện trong response."""

    mode: ChatResponseMode
    model: str | None = Field(min_length=1, max_length=255)


class ChatUsage(BaseModel):
    """Token usage chuẩn hóa; toàn object là null khi provider không cung cấp."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_total(self) -> "ChatUsage":
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens không được nhỏ hơn input + output")
        return self


class ChatError(BaseModel):
    """Lỗi public an toàn, không chứa raw provider response hay credentials."""

    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False


class ChatRequest(BaseModel):
    """Request cho POST /chat."""

    question: str = Field(..., min_length=1, description="Câu hỏi của người dùng")
    attachments: list[AttachmentReference] = Field(default_factory=list, max_length=20)
    session_id: UUID | None = Field(
        default=None,
        description="Có giá trị thì persist turn; bỏ trống giữ hành vi stateless cũ",
    )

    @model_validator(mode="after")
    def _validate_attachments(self):
        if self.attachments and self.session_id is None:
            raise ValueError("Attachments require a persistent session")
        keys = [(item.document_id, item.version_id) for item in self.attachments]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate attachments")
        return self

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Chuẩn hóa và từ chối câu hỏi rỗng/chỉ khoảng trắng."""
        value = value.strip()
        if not value:
            raise ValueError("question không được để trống")
        return value


class ChatResponse(BaseModel):
    """Logical JSON reply dùng chung làm nền cho JSON và SSE ở các task sau.

    Nullability:
    - stateless: ``session_id`` và hai message ID là null;
    - ``usage`` là null nếu provider không trả token accounting;
    - terminal success có ``error=null``; FAILED cần một ``error`` an toàn;
    - ``sources``/``citations`` luôn là array, có thể rỗng nhưng không null.
    """

    request_id: UUID
    session_id: UUID | None
    user_message_id: UUID | None
    assistant_message_id: UUID | None
    answer: str | None = Field(max_length=1_000_000)
    sources: list[Source]
    citations: list[Citation]
    metadata: ChatResponseMetadata
    usage: ChatUsage | None
    status: ChatResponseStatus
    error: ChatError | None

    @model_validator(mode="after")
    def _validate_reply_contract(self) -> "ChatResponse":
        message_ids = (self.user_message_id, self.assistant_message_id)
        if self.metadata.mode is ChatResponseMode.STATELESS:
            if self.session_id is not None or any(value is not None for value in message_ids):
                raise ValueError("stateless response không có session/message IDs")
        else:
            if self.session_id is None or any(value is None for value in message_ids):
                raise ValueError("persistent response cần session và đủ hai message IDs")

        if self.status is ChatResponseStatus.COMPLETED:
            if self.answer is None or not self.answer.strip():
                raise ValueError("COMPLETED response cần answer khác rỗng")
            if self.error is not None:
                raise ValueError("COMPLETED response phải có error=null")
        elif self.status is ChatResponseStatus.FAILED:
            if self.error is None:
                raise ValueError("FAILED response cần error an toàn")

        source_refs: set[tuple[str, str, str, int | None]] = set()
        for source in self.sources:
            try:
                source_refs.add(
                    (
                        str(UUID(str(source.chunk_id))),
                        str(UUID(str(source.document_id))),
                        str(UUID(str(source.version_id))),
                        source.page,
                    )
                )
            except (TypeError, ValueError):
                continue
        for citation in self.citations:
            citation_ref = (
                str(citation.chunk_id),
                str(citation.document_id),
                str(citation.version_id),
                citation.page,
            )
            if citation_ref not in source_refs:
                raise ValueError("citation phải tham chiếu một retrieved source thực")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "request_id": "11111111-1111-4111-8111-111111111111",
                    "session_id": None,
                    "user_message_id": None,
                    "assistant_message_id": None,
                    "answer": "Câu trả lời có căn cứ.",
                    "sources": [],
                    "citations": [],
                    "metadata": {"mode": "STATELESS", "model": "provider/model"},
                    "usage": None,
                    "status": "COMPLETED",
                    "error": None,
                }
            ]
        }
    }


class DocumentIndexInfo(BaseModel):
    """Kết quả tạo/index một document version."""

    document_id: str
    version_id: str
    job_id: str
    file_name: str
    num_chunks: int
    status: DocumentStatus = DocumentStatus.INDEXED
    activated: bool


class DocumentVersionInfo(BaseModel):
    version_id: str
    version: int
    file_name: str
    status: DocumentStatus
    checksum_sha256: str
    size_bytes: int
    chunk_count: int
    embedding_model: str | None = None
    created_at: datetime
    indexed_at: datetime | None = None


class DocumentInfo(BaseModel):
    """Thông tin identity và active version của document."""

    document_id: str
    file_name: str
    status: DocumentStatus
    active_version_id: str | None = None
    chunk_count: int
    version_count: int
    cleanup_pending: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class DocumentDetail(DocumentInfo):
    versions: list[DocumentVersionInfo]


class DeleteDocumentResponse(BaseModel):
    """Kết quả unpublish và cleanup retrieval data."""

    document_id: str
    status: DocumentStatus = DocumentStatus.DELETED
    deleted_chunks: int
    raw_file_policy: str = "retained"
    retained_files: int
    cleanup_pending: bool
    retrieval_eligible: bool = False
