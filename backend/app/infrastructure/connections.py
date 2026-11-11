"""Nhóm lifecycle MongoDB + Qdrant dùng chung cho `main.py` lifespan và scripts."""

from __future__ import annotations

from app.infrastructure.mongo import MongoDBConnection
from app.infrastructure.qdrant import QdrantConnection
from app.infrastructure.status import ConnectionStatus
from app.shared.config import Settings, settings


class CloudConnections:
    """Nhóm lifecycle của hai dịch vụ cloud, không thực hiện ghi dữ liệu."""

    def __init__(self, app_settings: Settings = settings) -> None:
        self.mongodb = MongoDBConnection(app_settings)
        self.qdrant = QdrantConnection(app_settings)

    def connect_all(self) -> dict[str, ConnectionStatus]:
        return {
            "mongodb": self.mongodb.connect(),
            "qdrant": self.qdrant.connect(),
        }

    def statuses(self) -> dict[str, ConnectionStatus]:
        return {"mongodb": self.mongodb.status, "qdrant": self.qdrant.status}

    def close(self) -> None:
        self.mongodb.close()
        self.qdrant.close()
