"""Storage port cho raw document.

Local adapter dùng storage key do hệ thống sinh, không dùng filename do người dùng
cung cấp. Contract không cho phép ghi đè để mỗi document version là immutable.
Concrete adapter nằm ở :mod:`app.infrastructure.storage`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Any, BinaryIO, Literal, Protocol, runtime_checkable
from uuid import UUID

_SAFE_TENANT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_EXTENSION_RE = re.compile(r"^\.[a-z0-9]{1,16}$")


class StorageError(Exception):
    """Base exception không làm lộ chi tiết filesystem nội bộ ra business layer."""


class InvalidStorageKeyError(StorageError):
    pass


class StorageAlreadyExistsError(StorageError):
    pass


class StorageNotFoundError(StorageError):
    pass


@dataclass(frozen=True, slots=True)
class StoredFile:
    storage_key: str
    checksum_sha256: str
    size_bytes: int


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol chung cho Local và S3 storage backend."""

    @property
    def backend_name(self) -> Literal["local", "s3"]:
        ...

    def put(
        self,
        key: str,
        data: bytes | bytearray | memoryview | BinaryIO,
        *,
        content_type: str | None = None,
    ) -> StoredFile:
        ...

    def get(self, key: str) -> bytes:
        ...

    def exists(self, key: str) -> bool:
        ...

    def delete_prefix(self, prefix: str) -> int:
        ...


class FileStorage(ABC):
    """Contract chung để business logic không phụ thuộc local filesystem/S3."""

    @property
    def backend_name(self) -> Literal["local", "s3"]:
        return "local"

    @abstractmethod
    def save(self, storage_key: str, content: bytes | bytearray | memoryview | BinaryIO) -> StoredFile:
        """Lưu content một lần và trả metadata đã tính trong khi ghi."""

    @abstractmethod
    def open(self, storage_key: str) -> BinaryIO:
        """Mở stream chỉ đọc; caller chịu trách nhiệm đóng stream."""

    @abstractmethod
    def read(self, storage_key: str) -> bytes:
        """Đọc toàn bộ object."""

    @abstractmethod
    def delete(self, storage_key: str) -> bool:
        """Xóa object chính xác; trả False nếu object không tồn tại."""

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Kiểm tra object có tồn tại hay không."""

    def put(
        self,
        key: str,
        data: bytes | bytearray | memoryview | BinaryIO,
        *,
        content_type: str | None = None,
    ) -> StoredFile:
        """Tương thích Protocol StorageBackend trên nền save()."""
        _ = content_type
        return self.save(key, data)

    def get(self, key: str) -> bytes:
        """Tương thích Protocol StorageBackend trên nền read()."""
        return self.read(key)

    def delete_prefix(self, prefix: str) -> int:
        """Xóa toàn bộ objects dưới prefix và trả số lượng đã xóa."""
        if self.delete(prefix):
            return 1
        return 0


def build_document_storage_key(document_id: str, version_id: str) -> str:
    """Sinh key versioned legacy chỉ từ UUID nội bộ, hoàn toàn độc lập filename."""
    try:
        canonical_document_id = str(UUID(document_id))
        canonical_version_id = str(UUID(version_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidStorageKeyError("document_id và version_id phải là UUID hợp lệ") from exc
    return f"documents/{canonical_document_id}/{canonical_version_id}/original"


def build_versioned_storage_key(
    tenant_id: str,
    document_id: str,
    version: int,
    file_name: str = "",
) -> str:
    """Sinh storage key chuẩn mới: {tenant}/{doc_id}/v{n}/original{ext}."""
    normalized_tenant = (tenant_id or "").strip() if isinstance(tenant_id, str) else ""
    if not _SAFE_TENANT_RE.fullmatch(normalized_tenant):
        raise InvalidStorageKeyError("tenant_id không hợp lệ")
    try:
        canonical_document_id = str(UUID(document_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidStorageKeyError("document_id phải là UUID hợp lệ") from exc
    if type(version) is not int or version < 1:
        raise InvalidStorageKeyError("version phải là số nguyên dương >= 1")

    suffix = ""
    if file_name:
        candidate_suffix = PurePosixPath(str(file_name)).suffix.lower()
        if candidate_suffix:
            if not _SAFE_EXTENSION_RE.fullmatch(candidate_suffix):
                raise InvalidStorageKeyError("Phần mở rộng file không hợp lệ")
            suffix = candidate_suffix

    return f"{normalized_tenant}/{canonical_document_id}/v{version}/original{suffix}"


def build_version_tables_prefix(
    tenant_id: str,
    document_id: str,
    version: int,
) -> str:
    """Sinh prefix thư mục chứa các file Parquet của 1 version: {tenant}/{doc_id}/v{n}/tables/."""
    normalized_tenant = (tenant_id or "").strip() if isinstance(tenant_id, str) else ""
    if not _SAFE_TENANT_RE.fullmatch(normalized_tenant):
        raise InvalidStorageKeyError("tenant_id không hợp lệ")
    try:
        canonical_document_id = str(UUID(document_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidStorageKeyError("document_id phải là UUID hợp lệ") from exc
    if type(version) is not int or version < 1:
        raise InvalidStorageKeyError("version phải là số nguyên dương >= 1")
    return f"{normalized_tenant}/{canonical_document_id}/v{version}/tables/"


def build_version_table_parquet_key(
    tenant_id: str,
    document_id: str,
    version: int,
    table_name: str,
) -> str:
    """Sinh storage key cho file Parquet của 1 bảng: {tenant}/{doc_id}/v{n}/tables/{table_name}.parquet."""
    prefix = build_version_tables_prefix(tenant_id, document_id, version)
    normalized_table = (table_name or "").strip() if isinstance(table_name, str) else ""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", normalized_table):
        raise InvalidStorageKeyError("table_name không hợp lệ")
    return f"{prefix}{normalized_table}.parquet"


class IngestionQueueError(Exception):
    """Raised when enqueuing an async ingestion job fails."""


class IngestionQueue(ABC):
    """Port gửi tác vụ ingestion bất đồng bộ tới background worker (ARQ/Redis)."""

    @abstractmethod
    async def enqueue_ingestion(self, *, version_id: str, job_id: str) -> str | None:
        """Đưa job xử lý document version vào hàng đợi và trả queue job ID."""

    async def close(self) -> None:
        """Đóng connection pool nếu adapter có giữ tài nguyên."""
        return None


class SqlEngineError(Exception):
    """Base exception an toàn cho thực thi SQL trên DuckDB, không lộ đường dẫn/credential."""


class SqlConfigurationError(SqlEngineError):
    """Raised when DuckDB/S3 read-only query executor is misconfigured."""


class SqlQueryTimeoutError(SqlEngineError):
    """Raised when a DuckDB SQL query exceeds duckdb_query_timeout_seconds."""


class SqlQueryExecutionError(SqlEngineError):
    """Raised when DuckDB rejects or fails executing a query (with safe hint for LLM)."""


@dataclass(frozen=True, slots=True)
class AuthorizedSqlTable:
    """Thông tin một bảng Parquet đã qua kiểm tra RBAC/scope để gắn TEMP VIEW trong DuckDB."""

    view_name: str
    parquet_key: str
    tenant_id: str
    document_id: str = ""
    version_id: str = ""
    file_name: str = ""
    sheet_name: str = ""
    columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SqlExecutionResult:
    """Kết quả thô đã giới hạn hàng và độ dài chuỗi từ SqlQueryExecutor."""

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool


@runtime_checkable
class SqlQueryExecutor(Protocol):
    """Port thực thi câu lệnh SELECT đã qua sql_guard trên DuckDB in-memory."""

    def execute(
        self,
        *,
        tables: Sequence[AuthorizedSqlTable],
        sql: str,
        tenant_id: str,
        max_rows: int | None = None,
        timeout_seconds: float | None = None,
    ) -> SqlExecutionResult:
        ...
