"""Storage abstraction cho raw document.

Local adapter dùng storage key do hệ thống sinh, không dùng filename do người dùng
cung cấp. Contract không cho phép ghi đè để mỗi document version là immutable.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from abc import ABC, abstractmethod
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import UUID

from app.config import PROJECT_ROOT, Settings, settings

_COPY_CHUNK_SIZE = 1024 * 1024


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


class LocalFileStorage(FileStorage):
    def __init__(self, root: str | Path):
        self._root = Path(root).expanduser().resolve()
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError("Không thể khởi tạo local storage") from exc

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, storage_key: str) -> Path:
        if not isinstance(storage_key, str) or not storage_key:
            raise InvalidStorageKeyError("storage_key không hợp lệ")
        if "\\" in storage_key:
            raise InvalidStorageKeyError("storage_key phải dùng POSIX separators")

        key = PurePosixPath(storage_key)
        if key.is_absolute() or any(part in ("", ".", "..") for part in key.parts):
            raise InvalidStorageKeyError("storage_key phải là relative path canonical")
        if any(":" in part for part in key.parts):
            raise InvalidStorageKeyError("storage_key chứa ký tự không hợp lệ")

        candidate = self._root.joinpath(*key.parts).resolve()
        if not candidate.is_relative_to(self._root):
            raise InvalidStorageKeyError("storage_key nằm ngoài storage root")
        return candidate

    @staticmethod
    def _write_content(
        destination: BinaryIO,
        content: bytes | bytearray | memoryview | BinaryIO,
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0

        if isinstance(content, (bytes, bytearray, memoryview)):
            chunks = (bytes(content),)
        elif callable(getattr(content, "read", None)):
            def stream_chunks():
                while True:
                    chunk = content.read(_COPY_CHUNK_SIZE)
                    if not chunk:
                        break
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise TypeError("Binary stream phải trả về bytes")
                    yield bytes(chunk)

            chunks = stream_chunks()
        else:
            raise TypeError("content phải là bytes hoặc binary stream")

        for chunk in chunks:
            destination.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        return digest.hexdigest(), size

    def save(self, storage_key: str, content: bytes | bytearray | memoryview | BinaryIO) -> StoredFile:
        target = self._resolve(storage_key)
        temporary_path: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                dir=target.parent,
                prefix=".storage-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                checksum, size = self._write_content(temporary, content)
                temporary.flush()
                os.fsync(temporary.fileno())

            # Hard-link publish là atomic và không thể ghi đè target đã tồn tại.
            os.link(temporary_path, target)
            return StoredFile(storage_key=storage_key, checksum_sha256=checksum, size_bytes=size)
        except FileExistsError as exc:
            raise StorageAlreadyExistsError("Storage key đã tồn tại và không được phép ghi đè") from exc
        except (OSError, TypeError) as exc:
            raise StorageError("Không thể lưu file") from exc
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)

    def open(self, storage_key: str) -> BinaryIO:
        target = self._resolve(storage_key)
        try:
            return target.open("rb")
        except FileNotFoundError as exc:
            raise StorageNotFoundError("Storage key không tồn tại") from exc
        except OSError as exc:
            raise StorageError("Không thể mở file") from exc

    def read(self, storage_key: str) -> bytes:
        with self.open(storage_key) as stored_file:
            try:
                return stored_file.read()
            except OSError as exc:
                raise StorageError("Không thể đọc file") from exc

    def delete(self, storage_key: str) -> bool:
        target = self._resolve(storage_key)
        try:
            target.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise StorageError("Không thể xóa file") from exc

    def exists(self, storage_key: str) -> bool:
        target = self._resolve(storage_key)
        try:
            return target.is_file()
        except OSError as exc:
            raise StorageError("Không thể kiểm tra file") from exc


def create_file_storage(config: Settings = settings) -> FileStorage:
    """Factory duy nhất mà business layer cần dùng; có thể thêm S3 adapter tại đây."""
    if config.storage_backend != "local":
        raise StorageError("Storage backend chưa được hỗ trợ")
    root = Path(config.documents_dir)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return LocalFileStorage(root)
