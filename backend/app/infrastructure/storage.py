"""Local filesystem adapter cho :class:`app.documents.ports.FileStorage`.

Local adapter dùng storage key do hệ thống sinh, không dùng filename do người dùng
cung cấp. Contract không cho phép ghi đè để mỗi document version là immutable.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Literal

from app.documents.ports import (
    FileStorage,
    InvalidStorageKeyError,
    StorageAlreadyExistsError,
    StorageError,
    StorageNotFoundError,
    StoredFile,
)
from app.infrastructure.s3_storage import S3FileStorage
from app.shared.config import PROJECT_ROOT, Settings, settings

_COPY_CHUNK_SIZE = 1024 * 1024


class LocalFileStorage(FileStorage):
    def __init__(self, root: str | Path):
        self._root = Path(root).expanduser().resolve()
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError("Không thể khởi tạo local storage") from exc

    @property
    def backend_name(self) -> Literal["local", "s3"]:
        return "local"

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

    def _delete_tree_files(self, directory: Path) -> int:
        deleted = 0
        for child in sorted(directory.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink()
                deleted += 1
            elif child.is_dir():
                with suppress(OSError):
                    child.rmdir()
        with suppress(OSError):
            directory.rmdir()
        return deleted

    def delete_prefix(self, prefix: str) -> int:
        if not isinstance(prefix, str) or not prefix.strip():
            raise InvalidStorageKeyError("storage_key không hợp lệ")
        if "\\" in prefix or prefix.startswith("/") or "//" in prefix.rstrip("/"):
            raise InvalidStorageKeyError("storage_key phải là relative path canonical")
        had_trailing_slash = prefix.endswith("/")
        stripped = prefix.rstrip("/")
        target = self._resolve(stripped)

        try:
            deleted = 0
            if had_trailing_slash:
                if target.is_dir():
                    return self._delete_tree_files(target)
                return 0

            if target.is_file():
                target.unlink()
                deleted += 1
            elif target.is_dir():
                deleted += self._delete_tree_files(target)

            parent = target.parent
            if parent.is_dir() and parent.is_relative_to(self._root):
                prefix_name = target.name
                for sibling in list(parent.iterdir()):
                    if sibling == target or not sibling.name.startswith(prefix_name):
                        continue
                    if sibling.is_file():
                        sibling.unlink()
                        deleted += 1
                    elif sibling.is_dir():
                        deleted += self._delete_tree_files(sibling)
            return deleted
        except OSError as exc:
            raise StorageError("Không thể xóa file theo prefix") from exc


def _unwrap_secret(value: Any) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    raw = getter() if callable(getter) else str(value)
    stripped = raw.strip()
    return stripped or None


def create_file_storage(
    config: Settings | Any = settings,
    *,
    backend: str | None = None,
    s3_client: Any = None,
) -> FileStorage:
    """Factory duy nhất mà business layer cần dùng cho Local và S3 storage."""
    selected = (
        backend
        if backend is not None
        else getattr(config, "storage_backend", "local")
    )
    selected_backend = str(selected or "").strip().lower()
    if selected_backend == "local":
        root = Path(getattr(config, "documents_dir", "./data/documents"))
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        return LocalFileStorage(root)

    if selected_backend == "s3":
        bucket = getattr(config, "s3_bucket", None)
        if not bucket or not str(bucket).strip():
            raise StorageError("Cần cấu hình S3_BUCKET khi dùng S3 storage backend")
        return S3FileStorage(
            bucket=str(bucket).strip(),
            region=str(getattr(config, "s3_region", "us-east-1") or "us-east-1"),
            endpoint_url=getattr(config, "s3_endpoint_url", None),
            access_key_id=_unwrap_secret(getattr(config, "s3_ingest_access_key_id", None)),
            secret_access_key=_unwrap_secret(
                getattr(config, "s3_ingest_secret_access_key", None)
            ),
            use_if_none_match=bool(getattr(config, "s3_use_if_none_match", True)),
            client=s3_client,
        )

    raise StorageError("Storage backend chưa được hỗ trợ")
