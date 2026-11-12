"""Multi-query expansion for enhanced retrieval coverage."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.rag.llm import get_llm
from app.shared.config import settings

logger = logging.getLogger(__name__)

MULTI_QUERY_SYSTEM_PROMPT = (
    "You are an AI language model assistant. Your task is to generate {count} "
    "different versions or search perspectives of the given user question to retrieve "
    "relevant documents from a vector database. By generating multiple perspectives, you help "
    "overcome limitations of keyword/distance-based similarity search.\n"
    "Requirements:\n"
    "- Generate each alternative query on a new line.\n"
    "- Do not number the output lines or include bullet points.\n"
    "- Do not add explanations or commentary.\n"
    "- Keep each query concise and focused on the user's intent."
)

_LINE_PREFIX_PATTERN = re.compile(r"^(?:\d+[\.\)]|\-|\*)\s*")


class MultiQueryExpander:
    """Expands a single retrieval query into multiple search queries."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        count: int = 3,
        timeout_seconds: float = 10.0,
        llm: Any = None,
    ) -> None:
        self.enabled = enabled
        self.count = max(1, count)
        self.timeout_seconds = timeout_seconds
        self._llm = llm

    def _get_llm(self) -> Any:
        return self._llm if self._llm is not None else get_llm()

    async def expand(self, query: str) -> list[str]:
        clean_query = query.strip()
        if not clean_query or not self.enabled:
            return [clean_query] if clean_query else []

        system_instruction = MULTI_QUERY_SYSTEM_PROMPT.format(count=self.count)
        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=clean_query),
        ]

        try:
            llm = self._get_llm()
            invoke_task = llm.ainvoke(messages)
            response = await asyncio.wait_for(invoke_task, timeout=self.timeout_seconds)
            text = (
                response.content
                if hasattr(response, "content") and isinstance(response.content, str)
                else str(response)
            )
            variations = self._parse_variations(text, clean_query)
            return [clean_query] + variations[: self.count]
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning("Multi-query expansion timed out after %.1fs", self.timeout_seconds)
            return [clean_query]
        except Exception as exc:
            logger.warning("Multi-query expansion failed: %s", exc)
            return [clean_query]

    @staticmethod
    def _parse_variations(text: str, original: str) -> list[str]:
        original_norm = original.casefold()
        variations: list[str] = []
        seen: set[str] = {original_norm}

        for raw_line in text.splitlines():
            line = _LINE_PREFIX_PATTERN.sub("", raw_line.strip()).strip("\"' ")
            if not line:
                continue
            norm = line.casefold()
            if norm not in seen:
                seen.add(norm)
                variations.append(line)

        return variations


def create_multi_query_expander(custom_settings: Any = None) -> MultiQueryExpander:
    active_settings = custom_settings or settings
    return MultiQueryExpander(
        enabled=getattr(active_settings, "multi_query_enabled", False),
        count=getattr(active_settings, "multi_query_count", 3),
        timeout_seconds=getattr(active_settings, "multi_query_timeout_seconds", 10.0),
    )
