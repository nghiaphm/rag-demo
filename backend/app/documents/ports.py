"""Storage port cho raw document.

Local adapter dùng storage key do hệ thống sinh, không dùng filename do người dùng
cung cấp. Contract không cho phép ghi đè để mỗi document version là immutable.
Concrete adapter nằm ở :mod:`app.infrastructure.storage`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO
from uuid import UUID


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


class FileStorage(ABC):
    """Contract chung để business logic không phụ thuộc local filesystem/S3."""

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


def build_document_storage_key(document_id: str, version_id: str) -> str:
    """Sinh key versioned chỉ từ UUID nội bộ, hoàn toàn độc lập filename."""
    try:
        canonical_document_id = str(UUID(document_id))
        canonical_version_id = str(UUID(version_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidStorageKeyError("document_id và version_id phải là UUID hợp lệ") from exc
    return f"documents/{canonical_document_id}/{canonical_version_id}/original"
