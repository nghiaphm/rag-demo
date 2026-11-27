"""Nhóm lifecycle MongoDB + Qdrant + optional dependencies dùng chung cho `main.py` lifespan và scripts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.infrastructure.mongo import MongoDBConnection
from app.infrastructure.qdrant import QdrantConnection
from app.infrastructure.s3_storage import _extract_s3_error_info
from app.infrastructure.status import ConnectionStatus
from app.shared.config import Settings, settings


def _unwrap_secret(value: Any) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    raw = getter() if callable(getter) else str(value)
    stripped = raw.strip()
    return stripped or None


def check_redis_health(app_settings: Settings) -> ConnectionStatus:
    """Kiểm tra kết nối Redis đồng bộ với timeout ngắn, không lộ URL/credentials."""
    redis_url = (app_settings.redis_url or "").strip()
    if not redis_url:
        return ConnectionStatus("redis", False, "not_configured", "Thiếu cấu hình Redis.")

    try:
        import redis
        from redis.exceptions import AuthenticationError, ResponseError
        from redis.exceptions import TimeoutError as RedisTimeoutError
    except ImportError:
        return ConnectionStatus("redis", False, "invalid_configuration", "Chưa cài đặt thư viện Redis.")

    client = None
    try:
        client = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        client.ping()
        return ConnectionStatus("redis", True, "connected", "Kết nối và xác thực thành công.")
    except AuthenticationError:
        return ConnectionStatus("redis", False, "authentication_failed", "Redis từ chối xác thực.")
    except ResponseError as exc:
        msg = str(exc).upper()
        if "AUTH" in msg or "NOAUTH" in msg or "WRONGPASS" in msg:
            return ConnectionStatus("redis", False, "authentication_failed", "Redis từ chối xác thực.")
        return ConnectionStatus("redis", False, "server_rejected", "Redis từ chối yêu cầu.")
    except (RedisTimeoutError, TimeoutError):
        return ConnectionStatus("redis", False, "timeout", "Redis không phản hồi trong thời hạn.")
    except Exception:
        return ConnectionStatus("redis", False, "connection_failed", "Không thể kết nối Redis.")
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def check_s3_health(app_settings: Settings) -> ConnectionStatus:
    """Kiểm tra quyền truy cập bucket S3 qua `head_bucket` mà không lộ tên bucket/endpoint."""
    bucket = (app_settings.s3_bucket or "").strip()
    if not bucket:
        return ConnectionStatus("s3", False, "not_configured", "Thiếu cấu hình S3.")

    try:
        import boto3
        from botocore.config import Config as BotocoreConfig
        from botocore.exceptions import ConnectTimeoutError, ReadTimeoutError
    except ImportError:
        return ConnectionStatus("s3", False, "invalid_configuration", "Chưa cài đặt thư viện S3.")

    kwargs: dict[str, Any] = {
        "region_name": (app_settings.s3_region or "us-east-1").strip() or "us-east-1",
        "config": BotocoreConfig(
            connect_timeout=3,
            read_timeout=3,
            retries={"max_attempts": 1},
        ),
    }
    if app_settings.s3_endpoint_url:
        kwargs["endpoint_url"] = app_settings.s3_endpoint_url
    access_key = _unwrap_secret(app_settings.s3_ingest_access_key_id)
    secret_key = _unwrap_secret(app_settings.s3_ingest_secret_access_key)
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key

    try:
        client = boto3.client("s3", **kwargs)
        client.head_bucket(Bucket=bucket)
        return ConnectionStatus("s3", True, "connected", "Kết nối và xác thực thành công.")
    except (ConnectTimeoutError, ReadTimeoutError, TimeoutError):
        return ConnectionStatus("s3", False, "timeout", "S3 không phản hồi trong thời hạn.")
    except Exception as exc:
        code, http_status = _extract_s3_error_info(exc)
        if http_status in {401, 403} or code in {
            "403",
            "AccessDenied",
            "InvalidAccessKeyId",
            "SignatureDoesNotMatch",
        }:
            return ConnectionStatus("s3", False, "authentication_failed", "S3 từ chối xác thực.")
        if http_status == 404 or code in {"404", "NoSuchBucket", "NotFound"}:
            return ConnectionStatus("s3", False, "invalid_configuration", "Cấu hình S3 không hợp lệ.")
        return ConnectionStatus("s3", False, "connection_failed", "Không thể kết nối S3.")


def is_readiness_ok(
    statuses: Mapping[str, ConnectionStatus],
    app_settings: Settings = settings,
) -> bool:
    """Đánh giá trạng thái tổng thể: phân biệt Required vs Optional dependencies.

    - Required (`mongodb`, `qdrant`): bất kỳ lỗi nào -> False (`503`).
    - Conditional blocking (`s3` khi `STORAGE_BACKEND=s3`, `redis` khi `ASYNC_INGESTION_ENABLED=true`): lỗi -> False (`503`).
    - Optional non-blocking (`redis` chỉ phục vụ `RATE_LIMIT_ENABLED=true`): cảnh báo trong `dependencies.redis` nhưng giữ True (`200`).
    """
    for required_name in ("mongodb", "qdrant"):
        item = statuses.get(required_name)
        if item is None or not item.ok:
            return False

    if str(app_settings.storage_backend).strip().lower() == "s3":
        s3_item = statuses.get("s3")
        if s3_item is not None and not s3_item.ok:
            return False

    if app_settings.async_ingestion_enabled:
        redis_item = statuses.get("redis")
        if redis_item is not None and not redis_item.ok:
            return False

    return True


class CloudConnections:
    """Nhóm lifecycle của các dịch vụ hạ tầng, không thực hiện ghi dữ liệu."""

    def __init__(
        self,
        app_settings: Settings = settings,
        *,
        redis_checker: Callable[[Settings], ConnectionStatus] = check_redis_health,
        s3_checker: Callable[[Settings], ConnectionStatus] = check_s3_health,
    ) -> None:
        self._settings = app_settings
        self._redis_checker = redis_checker
        self._s3_checker = s3_checker
        self.mongodb = MongoDBConnection(app_settings)
        self.qdrant = QdrantConnection(app_settings)

    def connect_all(self) -> dict[str, ConnectionStatus]:
        return {
            "mongodb": self.mongodb.connect(),
            "qdrant": self.qdrant.connect(),
        }

    def check_health_all(self) -> dict[str, ConnectionStatus]:
        """Kiểm tra non-destructive các dependencies bắt buộc và tùy chọn đang bật."""
        result: dict[str, ConnectionStatus] = {
            "mongodb": self.mongodb.check_health(),
            "qdrant": self.qdrant.check_health(),
        }
        if self._settings.rate_limit_enabled or self._settings.async_ingestion_enabled:
            result["redis"] = self._redis_checker(self._settings)
        if str(self._settings.storage_backend).strip().lower() == "s3":
            result["s3"] = self._s3_checker(self._settings)
        return result

    def statuses(self) -> dict[str, ConnectionStatus]:
        return {"mongodb": self.mongodb.status, "qdrant": self.qdrant.status}

    def close(self) -> None:
        self.mongodb.close()
        self.qdrant.close()
