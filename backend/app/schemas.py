"""Pydantic schemas cho request/response của FastAPI."""

from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    """Metadata nguồn của một chunk được retrieve."""

    file_name: str | None = None
    source: str | None = None
    document_id: str | None = None
    chunk_index: int | None = None
    page: int | None = None


class ChatRequest(BaseModel):
    """Request cho POST /chat."""

    question: str = Field(..., min_length=1, description="Câu hỏi của người dùng")

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
    """Kết quả index một document."""

    document_id: str
    file_name: str
    num_chunks: int


class DocumentInfo(BaseModel):
    """Thông tin một document đã index."""

    document_id: str
    file_name: str | None = None
    chunk_count: int


class DeleteDocumentResponse(BaseModel):
    """Kết quả xóa một document."""

    document_id: str
    deleted_chunks: int
