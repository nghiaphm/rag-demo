"""Tạo embedding thông qua LangChain Embeddings abstraction.

Baseline dùng provider API (Google Gemini, free tier) — KHÔNG self-host model.
Provider/model/API key đều lấy từ `settings`, không hard-code.
"""

from functools import lru_cache

from langchain_core.embeddings import Embeddings

from app.config import settings

_GOOGLE_PROVIDER_ALIASES: frozenset[str] = frozenset({"google", "google-genai", "gemini"})


@lru_cache
def get_embeddings() -> Embeddings:
    """Khởi tạo LangChain `Embeddings` theo `settings.embedding_provider`.

    Provider được chọn bằng config; model đổi bằng `EMBEDDING_MODEL` mà không
    phải sửa pipeline.

    Returns:
        Một đối tượng `Embeddings` của LangChain.

    Raises:
        ValueError: Nếu `settings.embedding_provider` không được hỗ trợ.
    """
    provider = settings.embedding_provider.strip().lower()
    if provider in _GOOGLE_PROVIDER_ALIASES:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=settings.embedding_api_key,
        )

    supported = ", ".join(sorted(_GOOGLE_PROVIDER_ALIASES))
    raise ValueError(
        f"Embedding provider '{settings.embedding_provider}' chưa được hỗ trợ. Hỗ trợ: {supported}"
    )
