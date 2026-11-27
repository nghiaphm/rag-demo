"""Client lifecycle và health check an toàn cho Qdrant Cloud.

Client dùng chung cho document lifecycle và Qdrant retrieval runtime.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.infrastructure.status import ConnectionStatus
from app.shared.config import Settings, settings


class QdrantConnection:
    """Quản lý một `QdrantClient` dùng chung và kiểm tra quyền list collections."""

    def __init__(
        self,
        app_settings: Settings = settings,
        client_factory: Callable[..., Any] = QdrantClient,
    ) -> None:
        self._settings = app_settings
        self._client_factory = client_factory
        self._lock = threading.RLock()
        self.client: Any | None = None
        self.status = ConnectionStatus("qdrant", False, "not_checked", "Chưa kiểm tra.")

    def _map_error(self, exc: Exception) -> ConnectionStatus:
        if isinstance(exc, UnexpectedResponse):
            code = "authentication_failed" if exc.status_code in {401, 403} else "server_rejected"
            return self._set_status(False, code, "Qdrant từ chối yêu cầu.")
        if isinstance(exc, (ResponseHandlingException, TimeoutError)):
            return self._set_status(False, "timeout_or_network", "Qdrant không phản hồi trong thời hạn.")
        return self._set_status(False, "connection_failed", "Không thể kết nối Qdrant.")

    def connect(self) -> ConnectionStatus:
        with self._lock:
            url = self._settings.qdrant_url
            api_key = self._settings.qdrant_api_key
            if url is None or api_key is None:
                return self._set_status(False, "not_configured", "Thiếu cấu hình Qdrant.")

            self.close()
            try:
                self.client = self._client_factory(
                    url=url.get_secret_value(),
                    api_key=api_key.get_secret_value(),
                    timeout=self._settings.qdrant_timeout_seconds,
                )
                self.client.get_collections()
                return self._set_status(True, "connected", "Kết nối và xác thực thành công.")
            except Exception as exc:  # SDK có thể bọc lỗi transport theo phiên bản
                self.close()
                return self._map_error(exc)

    def check_health(self) -> ConnectionStatus:
        """Kiểm tra kết nối trên client hiện hữu mà không đóng client đang phục vụ request."""
        with self._lock:
            url = self._settings.qdrant_url
            api_key = self._settings.qdrant_api_key
            if url is None or api_key is None:
                return self._set_status(False, "not_configured", "Thiếu cấu hình Qdrant.")

            if self.client is None:
                return self.connect()

            try:
                self.client.get_collections()
                return self._set_status(True, "connected", "Kết nối và xác thực thành công.")
            except Exception as exc:
                return self._map_error(exc)

    def close(self) -> None:
        with self._lock:
            if self.client is not None:
                self.client.close()
            self.client = None

    def _set_status(self, ok: bool, code: str, message: str) -> ConnectionStatus:
        self.status = ConnectionStatus("qdrant", ok, code, message)
        return self.status
