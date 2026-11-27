"""
Tập trung toàn bộ cấu hình của hệ thống tại 1 chỗ.

Mọi module khác phải import `settings` từ đây thay vì đọc `os.environ` trực tiếp.
Stack: FastAPI + LangChain + MongoDB Atlas + Qdrant Cloud + API-first
(Groq OpenAI-compatible API cho LLM, embedding provider gọi qua API).
"""

from functools import lru_cache
from pathlib import Path
import re
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env nằm ở project root (ngang hàng docker-compose.yml), không phụ thuộc CWD
# khi chạy `uvicorn` hay script từ thư mục nào.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # ----- LLM (Groq qua OpenAI-compatible API) -----
    groq_api_key: SecretStr
    openai_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_request_timeout_seconds: float = 60.0
    llm_max_retries: int = 2

    # JSON /chat only; SSE remains legacy until its separately approved integration.
    tool_use_enabled: bool = False

    # ----- Embedding provider (độc lập với LLM) -----
    # Baseline: Google Gemini embedding (free tier, gọi qua API — không self-host).
    embedding_provider: str = "google"
    embedding_api_key: SecretStr
    embedding_model: str = "gemini-embedding-001"
    embedding_timeout_seconds: float = 30.0

    # ----- Chunking -----
    chunk_size: int = 500
    chunk_overlap: int = 50
    parent_child_enabled: bool = False
    parent_chunk_size: int = 1200
    parent_chunk_overlap: int = 100
    child_chunk_size: int = 300
    child_chunk_overlap: int = 30

    # ----- Retrieval & Reranking -----
    top_k: int = 5
    reranker_enabled: bool = False
    reranker_provider: str = "flashrank"
    reranker_model: str = "ms-marco-TinyBERT-L-2-v2"
    reranker_candidate_top_k: int = 15
    reranker_relevance_threshold: float = 0.0
    cohere_api_key: SecretStr | None = None

    # ----- Multi-Query Expansion -----
    multi_query_enabled: bool = False
    multi_query_count: int = 3
    multi_query_timeout_seconds: float = 10.0

    # ----- Hybrid Search (Dense + Keyword BM25) -----
    hybrid_search_enabled: bool = False
    hybrid_rrf_k: int = 60

    # ----- History-aware context budget -----
    rag_context_window_tokens: int = 8192
    rag_system_max_tokens: int = 1024
    rag_history_max_tokens: int = 2048
    rag_chunks_max_tokens: int = 3584
    rag_query_max_tokens: int = 512
    rag_output_reserve_tokens: int = 1024
    rag_token_chars_per_token: float = 3.0
    rag_rewrite_timeout_seconds: float = 15.0
    rag_rewrite_max_chars: int = 1000

    # ----- Streaming -----
    stream_timeout_seconds: float = 120.0

    # ----- Tool orchestration & limits -----
    tool_selector_timeout_seconds: float = 15.0
    chat_turn_timeout_seconds: float = 120.0
    chat_max_answer_chars: int = 1_000_000
    provider_capability_status: str = "NOT_VERIFIED"

    # ----- Storage -----
    documents_dir: str = "./data/documents"
    storage_backend: str = "local"
    max_upload_bytes: int = 25 * 1024 * 1024
    default_tenant_id: str = "default"
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None
    s3_ingest_access_key_id: SecretStr | None = None
    s3_ingest_secret_access_key: SecretStr | None = None
    s3_use_if_none_match: bool = True

    # ----- Cloud persistence and retrieval -----
    mongodb_uri: SecretStr | None = None
    mongodb_db_name: str | None = None
    mongodb_timeout_ms: int = 5000
    qdrant_url: SecretStr | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "rag_documents"
    qdrant_timeout_seconds: float = 5.0

    # ----- Observability (Logging, Langfuse & Prometheus Metrics) -----
    log_level: str = "INFO"
    log_format: str = "json"
    metrics_enabled: bool = True
    langfuse_enabled: bool = False
    langfuse_trace_content_enabled: bool = False
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # ----- Corrective RAG (Phase 2) -----
    corrective_rag_enabled: bool = False
    corrective_max_retries: int = 1
    corrective_grader_model: str = "llama-3.1-8b-instant"
    web_search_fallback_enabled: bool = False
    tavily_api_key: SecretStr | None = None

    # ----- Agentic Orchestration (Phase 3) -----
    agentic_mode_enabled: bool = False
    max_agent_steps: int = 4

    # ----- Auth, RBAC, Semantic Cache & Rate Limiting (Phase 4) -----
    auth_enabled: bool = False
    jwt_secret_key: SecretStr = SecretStr("dev-insecure-secret-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_minutes: int = 60 * 24 * 7
    semantic_cache_enabled: bool = False
    semantic_cache_similarity_threshold: float = 0.95
    semantic_cache_ttl_seconds: int = 3600
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_enabled: bool = False
    rate_limit_requests_per_minute: int = 60
    trusted_proxy_ips: tuple[str, ...] | str = ()
    cors_origins: tuple[str, ...] | str = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    max_tokens_per_turn: int = 8192

    # ----- Async Ingestion Worker (Phase 5.1) -----
    async_ingestion_enabled: bool = False

    # ----- Excel Parquet & Table Catalog Ingestion -----
    excel_parquet_ingestion_enabled: bool = False
    excel_catalog_sample_rows: int = 3

    # ----- DuckDB SQL Executor & S3 Read-Only Query Credentials -----
    s3_query_access_key_id: SecretStr | None = None
    s3_query_secret_access_key: SecretStr | None = None
    duckdb_memory_limit: str = "512MB"
    duckdb_threads: int = 2
    duckdb_query_timeout_seconds: float = 15.0
    duckdb_max_rows: int = 200

    # ----- Excel SQL Chat Integration & Selective Text-Only Embedding -----
    excel_sql_enabled: bool = False
    excel_text_only_embedding_enabled: bool = False
    excel_sensitive_column_patterns: tuple[str, ...] | str = (
        "luong",
        "salary",
        "thu_nhap",
        "cmnd",
        "cccd",
        "passport",
        "so_tai_khoan",
        "bank",
        "mat_khau",
        "password",
        "token",
        "ma_so_thue",
        "dia_chi",
        "so_dien_thoai",
    )

    @field_validator("storage_backend")
    @classmethod
    def _validate_storage_backend(cls, value: str) -> str:
        backend = value.strip().lower()
        if backend not in ("local", "s3"):
            raise ValueError("STORAGE_BACKEND chỉ hỗ trợ 'local' hoặc 's3'")
        return backend

    @field_validator("default_tenant_id")
    @classmethod
    def _validate_default_tenant_id(cls, value: str) -> str:
        tenant = value.strip()
        if not tenant or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tenant):
            raise ValueError(
                "DEFAULT_TENANT_ID chỉ được chứa chữ, số, '_' hoặc '-' (1..64 ký tự)"
            )
        return tenant

    @field_validator("s3_bucket")
    @classmethod
    def _validate_s3_bucket(cls, value: str | None) -> str | None:
        if value is None:
            return None
        bucket = value.strip()
        if not bucket:
            return None
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
            raise ValueError("S3_BUCKET không hợp lệ")
        return bucket

    @field_validator("s3_region")
    @classmethod
    def _validate_s3_region(cls, value: str) -> str:
        region = value.strip()
        if not region:
            raise ValueError("S3_REGION không được rỗng")
        return region

    @field_validator("s3_endpoint_url")
    @classmethod
    def _validate_s3_endpoint_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = value.strip().rstrip("/")
        if not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("S3_ENDPOINT_URL phải là URL http/https hợp lệ")
        return url

    @field_validator("groq_api_key")
    @classmethod
    def _validate_groq_api_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret:
            raise ValueError("GROQ_API_KEY không được rỗng")
        return SecretStr(secret)

    @field_validator("embedding_api_key")
    @classmethod
    def _validate_embedding_api_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret:
            raise ValueError("EMBEDDING_API_KEY không được rỗng")
        return SecretStr(secret)

    @field_validator("llm_request_timeout_seconds", "embedding_timeout_seconds")
    @classmethod
    def _validate_provider_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Provider timeout phải lớn hơn 0")
        return value

    @field_validator("llm_max_retries")
    @classmethod
    def _validate_llm_max_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("LLM_MAX_RETRIES không được âm")
        return value

    @field_validator("max_upload_bytes")
    @classmethod
    def _validate_max_upload_bytes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_UPLOAD_BYTES phải lớn hơn 0")
        return value

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def _validate_trusted_proxy_ips(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        if isinstance(value, (list, tuple, set)):
            return tuple(str(part).strip() for part in value if str(part).strip())
        raise ValueError("TRUSTED_PROXY_IPS phải là chuỗi phân tách bằng dấu phẩy hoặc danh sách")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _validate_cors_origins(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            items = tuple(part.strip().rstrip("/") for part in value.split(",") if part.strip())
        elif isinstance(value, (list, tuple, set)):
            items = tuple(str(part).strip().rstrip("/") for part in value if str(part).strip())
        else:
            raise ValueError("CORS_ORIGINS phải là chuỗi phân tách bằng dấu phẩy hoặc danh sách")
        if not items:
            raise ValueError("CORS_ORIGINS không được rỗng")
        return items

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError("LOG_LEVEL phải là DEBUG, INFO, WARNING, ERROR hoặc CRITICAL")
        return level

    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, value: str) -> str:
        fmt = value.strip().lower()
        if fmt not in ("json", "text"):
            raise ValueError("LOG_FORMAT chỉ hỗ trợ 'json' hoặc 'text'")
        return fmt

    @field_validator("openai_base_url")
    @classmethod
    def _validate_openai_base_url(cls, value: str) -> str:
        url = value.strip().rstrip("/")
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.groq.com"
            or parsed.path != "/openai/v1"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "OPENAI_BASE_URL cho Groq phải là HTTPS API base kết thúc /openai/v1"
            )
        return url

    @field_validator("llm_model")
    @classmethod
    def _validate_llm_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("LLM_MODEL không được rỗng")
        return model

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

    @field_validator("stream_timeout_seconds")
    @classmethod
    def _validate_stream_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("STREAM_TIMEOUT_SECONDS phải lớn hơn 0")
        return value

    @field_validator("tool_selector_timeout_seconds", "chat_turn_timeout_seconds")
    @classmethod
    def _validate_chat_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Timeouts phải lớn hơn 0")
        return value

    @field_validator("chat_max_answer_chars")
    @classmethod
    def _validate_max_answer_chars(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("CHAT_MAX_ANSWER_CHARS phải lớn hơn 0")
        return value

    @field_validator("reranker_provider")
    @classmethod
    def _validate_reranker_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in ("flashrank", "cohere", "none"):
            raise ValueError("RERANKER_PROVIDER phải là 'flashrank', 'cohere' hoặc 'none'")
        return provider

    @field_validator("reranker_candidate_top_k")
    @classmethod
    def _validate_candidate_top_k(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("RERANKER_CANDIDATE_TOP_K phải lớn hơn 0")
        return value

    @field_validator("reranker_relevance_threshold")
    @classmethod
    def _validate_relevance_threshold(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            raise ValueError("RERANKER_RELEVANCE_THRESHOLD phải từ 0.0 đến 1.0")
        return value

    @field_validator("hybrid_rrf_k")
    @classmethod
    def _validate_hybrid_rrf_k(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("HYBRID_RRF_K phải lớn hơn 0")
        return value

    @field_validator(
        "rag_context_window_tokens",
        "rag_system_max_tokens",
        "rag_history_max_tokens",
        "rag_chunks_max_tokens",
        "rag_query_max_tokens",
        "rag_output_reserve_tokens",
    )
    @classmethod
    def _validate_token_budget_value(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Các giới hạn token phải lớn hơn 0")
        return value

    @field_validator("rag_token_chars_per_token")
    @classmethod
    def _validate_chars_per_token(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("RAG_TOKEN_CHARS_PER_TOKEN phải lớn hơn 0")
        return value

    @field_validator("rag_rewrite_timeout_seconds")
    @classmethod
    def _validate_rewrite_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("RAG_REWRITE_TIMEOUT_SECONDS phải lớn hơn 0")
        return value

    @field_validator("rag_rewrite_max_chars")
    @classmethod
    def _validate_rewrite_max_chars(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("RAG_REWRITE_MAX_CHARS phải lớn hơn 0")
        return value

    @field_validator("excel_catalog_sample_rows")
    @classmethod
    def _validate_excel_catalog_sample_rows(cls, value: int) -> int:
        if value < 0 or value > 20:
            raise ValueError("EXCEL_CATALOG_SAMPLE_ROWS phải từ 0 đến 20")
        return value

    @field_validator("duckdb_memory_limit")
    @classmethod
    def _validate_duckdb_memory_limit(cls, value: str) -> str:
        limit = value.strip().upper()
        if not re.fullmatch(r"\d+(?:MB|GB|KB|MIB|GIB)", limit):
            raise ValueError("DUCKDB_MEMORY_LIMIT phải có dạng số kèm đơn vị (ví dụ '512MB', '1GB')")
        return limit

    @field_validator("duckdb_threads")
    @classmethod
    def _validate_duckdb_threads(cls, value: int) -> int:
        if value < 1 or value > 32:
            raise ValueError("DUCKDB_THREADS phải từ 1 đến 32")
        return value

    @field_validator("duckdb_query_timeout_seconds")
    @classmethod
    def _validate_duckdb_query_timeout(cls, value: float) -> float:
        if value <= 0 or value > 120:
            raise ValueError("DUCKDB_QUERY_TIMEOUT_SECONDS phải lớn hơn 0 và không quá 120")
        return value

    @field_validator("duckdb_max_rows")
    @classmethod
    def _validate_duckdb_max_rows(cls, value: int) -> int:
        if value < 1 or value > 2000:
            raise ValueError("DUCKDB_MAX_ROWS phải từ 1 đến 2000")
        return value

    @field_validator("excel_sensitive_column_patterns", mode="before")
    @classmethod
    def _validate_excel_sensitive_column_patterns(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            items = [part.strip().lower() for part in value.split(",") if part.strip()]
            return tuple(items)
        if isinstance(value, (list, tuple, set)):
            items = [str(part).strip().lower() for part in value if str(part).strip()]
            return tuple(items)
        raise ValueError(
            "EXCEL_SENSITIVE_COLUMN_PATTERNS phải là chuỗi phân tách bằng dấu phẩy hoặc danh sách chuỗi"
        )

    @model_validator(mode="after")
    def _validate_context_budget_total(self) -> "Settings":
        allocated = (
            self.rag_system_max_tokens
            + self.rag_history_max_tokens
            + self.rag_chunks_max_tokens
            + self.rag_query_max_tokens
            + self.rag_output_reserve_tokens
        )
        if allocated > self.rag_context_window_tokens:
            raise ValueError(
                "Tổng system/history/chunks/query/output reserve vượt context window"
            )
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("Cần cấu hình S3_BUCKET khi STORAGE_BACKEND='s3'")
        if self.excel_sql_enabled:
            missing_flags: list[str] = []
            if not self.agentic_mode_enabled:
                missing_flags.append("AGENTIC_MODE_ENABLED=true")
            if not self.excel_parquet_ingestion_enabled:
                missing_flags.append("EXCEL_PARQUET_INGESTION_ENABLED=true")
            if missing_flags:
                raise ValueError(
                    "Khi EXCEL_SQL_ENABLED=true, bắt buộc phải bật các cấu hình sau: "
                    + ", ".join(missing_flags)
                )
        if self.excel_text_only_embedding_enabled and not self.excel_parquet_ingestion_enabled:
            raise ValueError(
                "Khi EXCEL_TEXT_ONLY_EMBEDDING_ENABLED=true, bắt buộc phải bật EXCEL_PARQUET_INGESTION_ENABLED=true"
            )
        if self.auth_enabled:
            jwt_secret = self.jwt_secret_key.get_secret_value().strip()
            weak_defaults = {
                "dev-insecure-secret-change-in-production",
                "replace-with-strong-random-secret",
                "changeme",
                "secret",
            }
            if len(jwt_secret) < 32 or jwt_secret.lower() in weak_defaults:
                raise ValueError(
                    "JWT_SECRET_KEY không an toàn khi AUTH_ENABLED=true; cần cấu hình khóa ngẫu nhiên tối thiểu 32 ký tự"
                )
        return self

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
#   from app.shared.config import settings
settings = get_settings()
