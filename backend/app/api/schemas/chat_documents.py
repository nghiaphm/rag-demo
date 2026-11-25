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


def _validate_app_route(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("route không được để trống")
    if not cleaned.startswith("/") or ".." in cleaned or "\\" in cleaned or any(ch.isspace() for ch in cleaned):
        raise ValueError("route phải là đường dẫn nội bộ hợp lệ bắt đầu bằng '/'")
    return cleaned


class ChatUiRelatedPage(BaseModel):
    """Trang liên quan hợp lệ có thể gợi ý cho người dùng chủ động chuyển hướng."""

    route: str = Field(..., min_length=1, max_length=120)
    title: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=240)

    @field_validator("route")
    @classmethod
    def _check_route(cls, value: str) -> str:
        return _validate_app_route(value)

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title không được để trống")
        return cleaned


class ChatUiDashboardKpi(BaseModel):
    """Chỉ số KPI đang hiển thị trên trang Dashboard HR."""

    label: str = Field(..., min_length=1, max_length=120)
    value: str = Field(..., min_length=1, max_length=64)
    delta_label: str | None = Field(default=None, max_length=160)
    trend: Literal["up", "down", "neutral"] | None = None
    helper_text: str | None = Field(default=None, max_length=200)

    @field_validator("label", "value")
    @classmethod
    def _check_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Trường KPI không được để trống")
        return cleaned


class ChatUiDashboardDepartment(BaseModel):
    """Số liệu phân bổ nhân sự theo phòng ban trên Dashboard HR."""

    department: str = Field(..., min_length=1, max_length=120)
    count: int = Field(..., ge=0, le=1_000_000)
    open_roles: int = Field(default=0, ge=0, le=100_000)

    @field_validator("department")
    @classmethod
    def _check_department(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Tên phòng ban không được để trống")
        return cleaned


class ChatUiDashboardContractStatus(BaseModel):
    """Số liệu phân bổ trạng thái/loại hợp đồng trên Dashboard HR."""

    label: str = Field(..., min_length=1, max_length=120)
    count: int = Field(..., ge=0, le=1_000_000)

    @field_validator("label")
    @classmethod
    def _check_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Nhãn loại hợp đồng không được để trống")
        return cleaned


class ChatUiDashboardKnowledgeBase(BaseModel):
    """Thống kê Kho tri thức RAG thực tế đang hiển thị trên Dashboard HR."""

    total_documents: int = Field(..., ge=0, le=1_000_000)
    indexed_documents: int = Field(..., ge=0, le=1_000_000)
    processing_documents: int = Field(..., ge=0, le=1_000_000)
    failed_documents: int = Field(..., ge=0, le=1_000_000)
    total_chunks: int = Field(..., ge=0, le=100_000_000)


class ChatUiDashboardSnapshot(BaseModel):
    """Ảnh chụp số liệu có cấu trúc của trang Dashboard HR phục vụ phân tích thống kê."""

    as_of_label: str = Field(..., min_length=1, max_length=160)
    total_employees: int = Field(..., ge=0, le=1_000_000)
    kpis: list[ChatUiDashboardKpi] = Field(default_factory=list, max_length=12)
    departments: list[ChatUiDashboardDepartment] = Field(default_factory=list, max_length=30)
    contract_statuses: list[ChatUiDashboardContractStatus] = Field(default_factory=list, max_length=12)
    knowledge_base: ChatUiDashboardKnowledgeBase | None = None

    @field_validator("as_of_label")
    @classmethod
    def _check_as_of_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("as_of_label không được để trống")
        return cleaned


class ChatUiContext(BaseModel):
    """Ngữ cảnh giao diện HR tùy chọn truyền từ Frontend."""

    portal: Literal["hr"] = "hr"
    route: str = Field(..., min_length=1, max_length=120)
    page_title: str = Field(..., min_length=1, max_length=120)
    page_purpose: str = Field(..., min_length=1, max_length=400)
    available_features: list[str] = Field(default_factory=list, max_length=12)
    related_pages: list[ChatUiRelatedPage] = Field(default_factory=list, max_length=6)
    selected_document_name: str | None = Field(default=None, max_length=255)
    selected_category: str | None = Field(default=None, max_length=64)
    dashboard_snapshot: ChatUiDashboardSnapshot | None = None

    @field_validator("route")
    @classmethod
    def _check_route(cls, value: str) -> str:
        return _validate_app_route(value)

    @field_validator("page_title", "page_purpose")
    @classmethod
    def _check_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Trường ngữ cảnh trang không được rỗng")
        return cleaned

    @field_validator("available_features")
    @classmethod
    def _check_features(cls, items: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in items:
            cleaned = item.strip()
            if not cleaned:
                raise ValueError("Mục chức năng không được rỗng")
            if len(cleaned) > 200:
                raise ValueError("Mục chức năng vượt quá 200 ký tự")
            normalized.append(cleaned)
        return normalized


class ChatRequest(BaseModel):
    """Request cho POST /chat."""

    question: str = Field(..., min_length=1, description="Câu hỏi của người dùng")
    attachments: list[AttachmentReference] = Field(default_factory=list, max_length=20)
    session_id: UUID | None = Field(
        default=None,
        description="Có giá trị thì persist turn; bỏ trống giữ hành vi stateless cũ",
    )
    ui_context: ChatUiContext | None = Field(
        default=None,
        description="Ngữ cảnh trang HR Portal hiện tại; bỏ trống giữ hành vi RAG Workspace chuẩn",
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
