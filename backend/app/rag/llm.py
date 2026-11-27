"""Tạo LLM qua Groq OpenAI-compatible API bằng LangChain ChatOpenAI.

Provider/model/API key/base URL đều lấy từ settings, không hard-code credentials.
"""

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.shared.config import settings


@lru_cache
def get_llm() -> BaseChatModel:
    """Khởi tạo `ChatOpenAI` trỏ tới Groq theo `settings`.

    Đổi model chỉ cần sửa `LLM_MODEL`; không phải sửa chain/pipeline.
    """
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.groq_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
    )


@lru_cache
def get_grader_llm() -> BaseChatModel:
    """Khởi tạo lightweight LLM cho Corrective RAG grading/query correction.

    Dùng `settings.corrective_grader_model` với `temperature=0.0` để đảm bảo tính tất định.
    """
    return ChatOpenAI(
        model=settings.corrective_grader_model,
        api_key=settings.groq_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        temperature=0.0,
    )
