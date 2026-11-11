"""Pydantic models cho document metadata trong MongoDB Atlas.

Các ID dùng UUID v4 dạng chuỗi canonical để ổn định xuyên MongoDB, Qdrant và API.
Datetime luôn timezone-aware và được chuẩn hóa về UTC.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid4())


def _canonical_uuid(value: str) -> str:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("ID phải là UUID hợp lệ") from exc
    return str(parsed)


class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    DELETED = "DELETED"


class IngestionJobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MongoRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, validate_default=True)

    def to_mongo(self) -> dict[str, Any]:
        """Trả document tương thích PyMongo, giữ `datetime` native và dùng alias `_id`."""
        return self.model_dump(mode="python", by_alias=True)


class DocumentRecord(MongoRecord):
    """Identity ổn định của một document, độc lập filename và các version."""

    document_id: str = Field(default_factory=new_uuid, alias="_id")
    file_name: str = Field(min_length=1, max_length=255)
    source_key: str | None = Field(default=None, min_length=1, max_length=512)
    active_version_id: str | None = None
    status: DocumentStatus = DocumentStatus.UPLOADED
    cleanup_pending: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    deleted_at: datetime | None = None

    _validate_document_id = field_validator("document_id")(_canonical_uuid)
    _validate_active_version_id = field_validator("active_version_id")(
        lambda value: None if value is None else _canonical_uuid(value)
    )

    @field_validator("source_key")
    @classmethod
    def _normalize_source_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_key không được rỗng")
        return normalized

    @field_validator("created_at", "updated_at", "deleted_at")
    @classmethod
    def _normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime phải có timezone")
        return value.astimezone(timezone.utc)


class DocumentVersionRecord(MongoRecord):
    """Một immutable source version thuộc document identity."""

    version_id: str = Field(default_factory=new_uuid, alias="_id")
    document_id: str
    version: int = Field(ge=1)
    file_name: str = Field(min_length=1, max_length=255)
    checksum_sha256: str
    size_bytes: int = Field(ge=0)
    storage_key: str | None = Field(default=None, min_length=1, max_length=1024)
    chunk_count: int = Field(default=0, ge=0)
    embedding_model: str | None = Field(default=None, min_length=1, max_length=255)
    vector_collection: str | None = Field(default=None, min_length=1, max_length=255)
    status: DocumentStatus = DocumentStatus.UPLOADED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    indexed_at: datetime | None = None

    _validate_version_id = field_validator("version_id")(_canonical_uuid)
    _validate_document_id = field_validator("document_id")(_canonical_uuid)

    @field_validator("checksum_sha256")
    @classmethod
    def _validate_checksum(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("checksum_sha256 phải gồm đúng 64 ký tự hex")
        return normalized

    @field_validator("created_at", "updated_at", "indexed_at")
    @classmethod
    def _normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime phải có timezone")
        return value.astimezone(timezone.utc)


class IngestionJobRecord(MongoRecord):
    """Trạng thái một lần xử lý version; cho phép retry bằng job ID mới."""

    job_id: str = Field(default_factory=new_uuid, alias="_id")
    document_id: str
    version_id: str
    status: IngestionJobStatus = IngestionJobStatus.PENDING
    attempt: int = Field(default=1, ge=1)
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    _validate_job_id = field_validator("job_id")(_canonical_uuid)
    _validate_document_id = field_validator("document_id")(_canonical_uuid)
    _validate_version_id = field_validator("version_id")(_canonical_uuid)

    @field_validator("created_at", "updated_at", "started_at", "completed_at")
    @classmethod
    def _normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime phải có timezone")
        return value.astimezone(timezone.utc)
