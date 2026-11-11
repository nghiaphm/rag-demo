"""Client lifecycle và health check an toàn cho MongoDB Atlas.

Client dùng chung cho document lifecycle và conversation persistence.
"""

from __future__ import annotations

from typing import Any, Callable

from pymongo import MongoClient
from pymongo.errors import (
    ConfigurationError,
    NetworkTimeout,
    OperationFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from app.infrastructure.status import ConnectionStatus
from app.shared.config import Settings, settings


class MongoDBConnection:
    """Quản lý một `MongoClient` dùng chung và ping Atlas với timeout hữu hạn."""

    def __init__(
        self,
        app_settings: Settings = settings,
        client_factory: Callable[..., Any] = MongoClient,
    ) -> None:
        self._settings = app_settings
        self._client_factory = client_factory
        self.client: Any | None = None
        self.database: Any | None = None
        self.status = ConnectionStatus("mongodb", False, "not_checked", "Chưa kiểm tra.")

    def connect(self) -> ConnectionStatus:
        uri = self._settings.mongodb_uri
        db_name = self._settings.mongodb_db_name
        if uri is None or db_name is None:
            return self._set_status(False, "not_configured", "Thiếu cấu hình MongoDB.")

        self.close()
        try:
            timeout_ms = self._settings.mongodb_timeout_ms
            self.client = self._client_factory(
                uri.get_secret_value(),
                appname="rag-demo",
                connectTimeoutMS=timeout_ms,
                serverSelectionTimeoutMS=timeout_ms,
                socketTimeoutMS=timeout_ms,
                timeoutMS=timeout_ms,
                tz_aware=True,
            )
            self.client.admin.command("ping")
            self.database = self.client[db_name]
            return self._set_status(True, "connected", "Kết nối và xác thực thành công.")
        except OperationFailure as exc:
            self.close()
            # Atlas uses code 8000/AtlasError for bad database-user credentials;
            # standalone MongoDB commonly uses 18 (AuthenticationFailed).
            code = "authentication_failed" if exc.code in {13, 18, 8000} else "server_rejected"
            return self._set_status(False, code, "MongoDB từ chối yêu cầu.")
        except (NetworkTimeout, ServerSelectionTimeoutError):
            self.close()
            return self._set_status(False, "timeout", "MongoDB không phản hồi trong thời hạn.")
        except ConfigurationError:
            self.close()
            return self._set_status(False, "invalid_configuration", "Cấu hình MongoDB không hợp lệ.")
        except PyMongoError:
            self.close()
            return self._set_status(False, "connection_failed", "Không thể kết nối MongoDB.")

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
        self.client = None
        self.database = None

    def _set_status(self, ok: bool, code: str, message: str) -> ConnectionStatus:
        self.status = ConnectionStatus("mongodb", ok, code, message)
        return self.status
