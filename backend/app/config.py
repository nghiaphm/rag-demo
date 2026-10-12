"""
Tập trung toàn bộ cấu hình của hệ thống tại 1 chỗ.

Mọi module khác phải import `settings` từ đây thay vì đọc `os.environ` trực tiếp.
Stack: FastAPI + LangChain + MongoDB Atlas + Qdrant Cloud + API-first
(OpenRouter cho LLM, embedding provider gọi qua API).
"""

from functools import lru_cache
from pathlib import Path
import re
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env nằm ở project root (ngang hàng docker-compose.yml), không phụ thuộc CWD
# khi chạy `uvicorn` hay script từ thư mục nào.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # ----- LLM (OpenRouter) -----
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b:free"

    # ----- Embedding provider (độc lập với LLM) -----
    # Baseline: Google Gemini embedding (free tier, gọi qua API — không self-host).
    embedding_provider: str = "google"
    embedding_api_key: str
    embedding_model: str = "gemini-embedding-001"

    # ----- Chunking -----
    chunk_size: int = 500
    chunk_overlap: int = 50

    # ----- Retrieval -----
    top_k: int = 5

    # ----- Storage -----
    documents_dir: str = "./data/documents"
    storage_backend: str = "local"

    # ----- Cloud persistence and retrieval -----
    mongodb_uri: SecretStr | None = None
    mongodb_db_name: str | None = None
    mongodb_timeout_ms: int = 5000
    qdrant_url: SecretStr | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "rag_documents"
    qdrant_timeout_seconds: float = 5.0

    @field_validator("storage_backend")
    @classmethod
    def _validate_storage_backend(cls, value: str) -> str:
        backend = value.strip().lower()
        if backend != "local":
            raise ValueError("STORAGE_BACKEND hiện chỉ hỗ trợ giá trị 'local'")
        return backend

    @field_validator("mongodb_uri")
    @classmethod
    def _validate_mongodb_uri(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        uri = value.get_secret_value().strip()
        if not uri:
            return None
        if not uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGODB_URI phải dùng mongodb:// hoặc mongodb+srv://")
        return SecretStr(uri)

    @field_validator("mongodb_db_name")
    @classmethod
    def _validate_mongodb_db_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            return None
        if any(char in name for char in ('/', '\\', '.', ' ', '"', '$')):
            raise ValueError("MONGODB_DB_NAME chứa ký tự không hợp lệ")
        return name

    @field_validator("qdrant_url")
    @classmethod
    def _validate_qdrant_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        url = value.get_secret_value().strip().rstrip("/")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("QDRANT_URL cloud phải là URL HTTPS hợp lệ")
        return SecretStr(url)

    @field_validator("qdrant_collection")
    @classmethod
    def _validate_qdrant_collection(cls, value: str) -> str:
        name = value.strip()
        if not name or not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", name):
            raise ValueError("QDRANT_COLLECTION chỉ được chứa chữ, số, '_' hoặc '-'")
        return name

    @field_validator("mongodb_timeout_ms")
    @classmethod
    def _validate_mongodb_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MONGODB_TIMEOUT_MS phải lớn hơn 0")
        return value

    @field_validator("qdrant_timeout_seconds")
    @classmethod
    def _validate_qdrant_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("QDRANT_TIMEOUT_SECONDS phải lớn hơn 0")
        return value

    # Đọc từ file .env, không phân biệt hoa/thường tên biến.
    # extra="ignore" để biến môi trường lạ/cũ không làm app crash.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Dùng lru_cache để Settings chỉ được khởi tạo (đọc .env) đúng 1 lần,
    các lần gọi get_settings() sau chỉ trả về lại object đã có sẵn.
    """
    return Settings()


# Import trực tiếp settings ở các file khác cho gọn:
#   from app.config import settings
settings = get_settings()
