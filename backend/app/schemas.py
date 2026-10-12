"""Pydantic schemas cho request/response của FastAPI."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.document_models import DocumentStatus


class Source(BaseModel):
    """Metadata nguồn của một chunk được retrieve."""

    file_name: str | None = None
    source: str | None = None
    document_id: str | None = None
    version_id: str | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None
    page: int | None = None


class ChatRequest(BaseModel):
    """Request cho POST /chat."""

    question: str = Field(..., min_length=1, description="Câu hỏi của người dùng")
    session_id: UUID | None = Field(
        default=None,
        description="Có giá trị thì persist turn; bỏ trống giữ hành vi stateless cũ",
    )

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Chuẩn hóa và từ chối câu hỏi rỗng/chỉ khoảng trắng."""
        value = value.strip()
        if not value:
            raise ValueError("question không được để trống")
        return value


class ChatResponse(BaseModel):
    """Response cho POST /chat."""

    answer: str
    sources: list[Source]


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
