"""S3 adapter cho :class:`app.documents.ports.FileStorage` và :class:`app.documents.ports.StorageBackend`.

Mọi thông báo lỗi đều được chuẩn hóa an toàn, tuyệt đối không log hoặc làm lộ
access key, secret key, endpoint nội bộ hay chi tiết exception của SDK ra ngoài.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import PurePosixPath
from typing import Any, BinaryIO, Literal

from app.documents.ports import (
    FileStorage,
    InvalidStorageKeyError,
    StorageAlreadyExistsError,
    StorageError,
    StorageNotFoundError,
    StoredFile,
)

_COPY_CHUNK_SIZE = 1024 * 1024
_S3_DELETE_BATCH_SIZE = 1000


def _extract_s3_error_info(exc: Exception) -> tuple[str, int | None]:
    """Trích mã lỗi S3/HTTP status an toàn từ botocore ClientError hoặc stub."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return "", None
    error_block = response.get("Error")
    code = ""
    if isinstance(error_block, dict):
        raw_code = error_block.get("Code")
        if raw_code is not None:
            code = str(raw_code).strip()
    meta = response.get("ResponseMetadata")
    status_code: int | None = None
    if isinstance(meta, dict):
        raw_status = meta.get("HTTPStatusCode")
        if isinstance(raw_status, int):
            status_code = raw_status
    return code, status_code


def _is_not_found_error(exc: Exception) -> bool:
    code, status = _extract_s3_error_info(exc)
    return status == 404 or code in {"404", "NoSuchKey", "NotFound"}


def _is_precondition_failed_error(exc: Exception) -> bool:
    code, status = _extract_s3_error_info(exc)
    return status in {409, 412} or code in {
        "412",
        "PreconditionFailed",
        "ConditionalRequestConflict",
    }


class S3FileStorage(FileStorage):
    """Concrete S3 storage backend hỗ trợ conditional put và delete_prefix."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        use_if_none_match: bool = True,
        client: Any = None,
    ) -> None:
        normalized_bucket = (bucket or "").strip()
        if not normalized_bucket:
            raise StorageError("Thiếu cấu hình S3_BUCKET cho S3 storage backend")
        self._bucket = normalized_bucket
        self._region = (region or "us-east-1").strip() or "us-east-1"
        self._endpoint_url = endpoint_url.strip() if endpoint_url else None
        self._use_if_none_match = bool(use_if_none_match)
        self._client = client if client is not None else self._create_boto3_client(
            region=self._region,
            endpoint_url=self._endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )

    @staticmethod
    def _create_boto3_client(
        *,
        region: str,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
    ) -> Any:
        try:
            import boto3
        except ImportError as exc:
            raise StorageError("Chưa cài đặt thư viện boto3 cho S3 storage backend") from exc

        kwargs: dict[str, Any] = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key_id and secret_access_key:
            kwargs["aws_access_key_id"] = access_key_id
            kwargs["aws_secret_access_key"] = secret_access_key

        try:
            return boto3.client("s3", **kwargs)
        except Exception:
            raise StorageError("Không thể khởi tạo kết nối S3 storage backend") from None

    @property
    def backend_name(self) -> Literal["local", "s3"]:
        return "s3"

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def use_if_none_match(self) -> bool:
        return self._use_if_none_match

    @staticmethod
    def _normalize_key(storage_key: str, *, allow_directory_prefix: bool = False) -> str:
        if not isinstance(storage_key, str) or not storage_key.strip():
            raise InvalidStorageKeyError("storage_key không hợp lệ")
        if "\\" in storage_key:
            raise InvalidStorageKeyError("storage_key phải dùng POSIX separators")

        had_trailing_slash = storage_key.endswith("/")
        stripped = storage_key.rstrip("/") if allow_directory_prefix else storage_key
        if not stripped or stripped.startswith("/") or "//" in stripped:
            raise InvalidStorageKeyError("storage_key phải là relative path canonical")

        key = PurePosixPath(stripped)
        if key.is_absolute() or any(part in ("", ".", "..") for part in key.parts):
            raise InvalidStorageKeyError("storage_key phải là relative path canonical")
        if any(":" in part for part in key.parts):
            raise InvalidStorageKeyError("storage_key chứa ký tự không hợp lệ")

        normalized = key.as_posix()
        if allow_directory_prefix and had_trailing_slash:
            return f"{normalized}/"
        return normalized

    @staticmethod
    def _read_bytes_and_hash(
        content: bytes | bytearray | memoryview | BinaryIO,
    ) -> tuple[bytes, str, int]:
        digest = hashlib.sha256()
        buffer = io.BytesIO()

        if isinstance(content, (bytes, bytearray, memoryview)):
            raw = bytes(content)
            digest.update(raw)
            return raw, digest.hexdigest(), len(raw)

        if callable(getattr(content, "read", None)):
            try:
                while True:
                    chunk = content.read(_COPY_CHUNK_SIZE)
                    if not chunk:
                        break
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise TypeError("Binary stream phải trả về bytes")
                    chunk_bytes = bytes(chunk)
                    buffer.write(chunk_bytes)
                    digest.update(chunk_bytes)
            except (OSError, TypeError) as exc:
                raise StorageError("Không thể đọc dữ liệu nguồn để lưu lên S3") from exc
            raw = buffer.getvalue()
            return raw, digest.hexdigest(), len(raw)

        raise StorageError("content phải là bytes hoặc binary stream")

    def put(
        self,
        key: str,
        data: bytes | bytearray | memoryview | BinaryIO,
        *,
        content_type: str | None = None,
    ) -> StoredFile:
        normalized_key = self._normalize_key(key)
        payload, checksum, size = self._read_bytes_and_hash(data)

        if not self._use_if_none_match:
            if self.exists(normalized_key):
                raise StorageAlreadyExistsError(
                    "Storage key đã tồn tại và không được phép ghi đè"
                )

        put_kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": normalized_key,
            "Body": payload,
        }
        if content_type:
            put_kwargs["ContentType"] = content_type
        if self._use_if_none_match:
            put_kwargs["IfNoneMatch"] = "*"

        try:
            self._client.put_object(**put_kwargs)
        except StorageError:
            raise
        except Exception as exc:
            if _is_precondition_failed_error(exc):
                raise StorageAlreadyExistsError(
                    "Storage key đã tồn tại và không được phép ghi đè"
                ) from None
            raise StorageError("Không thể lưu file lên S3") from None

        return StoredFile(
            storage_key=normalized_key,
            checksum_sha256=checksum,
            size_bytes=size,
        )

    def save(
        self,
        storage_key: str,
        content: bytes | bytearray | memoryview | BinaryIO,
    ) -> StoredFile:
        return self.put(storage_key, content)

    def get(self, key: str) -> bytes:
        normalized_key = self._normalize_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=normalized_key)
            body = response["Body"]
            try:
                data = body.read()
            finally:
                close_fn = getattr(body, "close", None)
                if callable(close_fn):
                    close_fn()
            if not isinstance(data, (bytes, bytearray, memoryview)):
                raise StorageError("Phản hồi S3 không hợp lệ")
            return bytes(data)
        except StorageError:
            raise
        except Exception as exc:
            if _is_not_found_error(exc):
                raise StorageNotFoundError("Storage key không tồn tại") from None
            raise StorageError("Không thể đọc file từ S3") from None

    def read(self, storage_key: str) -> bytes:
        return self.get(storage_key)

    def open(self, storage_key: str) -> BinaryIO:
        return io.BytesIO(self.get(storage_key))

    def exists(self, storage_key: str) -> bool:
        normalized_key = self._normalize_key(storage_key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=normalized_key)
            return True
        except Exception as exc:
            if _is_not_found_error(exc):
                return False
            raise StorageError("Không thể kiểm tra file trên S3") from None

    def delete(self, storage_key: str) -> bool:
        normalized_key = self._normalize_key(storage_key)
        if not self.exists(normalized_key):
            return False
        try:
            self._client.delete_object(Bucket=self._bucket, Key=normalized_key)
            return True
        except Exception:
            raise StorageError("Không thể xóa file trên S3") from None

    def delete_prefix(self, prefix: str) -> int:
        normalized_prefix = self._normalize_key(prefix, allow_directory_prefix=True)
        deleted_total = 0
        continuation_token: str | None = None

        try:
            while True:
                list_kwargs: dict[str, Any] = {
                    "Bucket": self._bucket,
                    "Prefix": normalized_prefix,
                }
                if continuation_token:
                    list_kwargs["ContinuationToken"] = continuation_token
                page = self._client.list_objects_v2(**list_kwargs)
                contents = page.get("Contents") or []
                keys = [
                    item["Key"]
                    for item in contents
                    if isinstance(item, dict) and isinstance(item.get("Key"), str)
                ]
                for idx in range(0, len(keys), _S3_DELETE_BATCH_SIZE):
                    batch = [{"Key": k} for k in keys[idx : idx + _S3_DELETE_BATCH_SIZE]]
                    if not batch:
                        continue
                    self._client.delete_objects(
                        Bucket=self._bucket,
                        Delete={"Objects": batch, "Quiet": True},
                    )
                    deleted_total += len(batch)

                if not page.get("IsTruncated"):
                    break
                continuation_token = page.get("NextContinuationToken")
                if not continuation_token:
                    break
        except StorageError:
            raise
        except Exception:
            raise StorageError("Không thể xóa danh sách file theo prefix trên S3") from None

        return deleted_total
