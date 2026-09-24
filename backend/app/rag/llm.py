"""Tạo LLM (Chat Model) qua LangChain integration cho OpenRouter.

Baseline dùng free model qua OpenRouter (API-first, không self-host).
Model/API key/base URL lấy từ `settings`, không hard-code.
"""

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openrouter import ChatOpenRouter

from app.config import settings


@lru_cache
def get_llm() -> BaseChatModel:
    """Khởi tạo `ChatOpenRouter` theo `settings`.

    Đổi model chỉ cần sửa `LLM_MODEL`; không phải sửa chain/pipeline.
    """
    return ChatOpenRouter(
        model=settings.llm_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
