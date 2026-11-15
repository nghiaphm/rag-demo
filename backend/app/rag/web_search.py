"""Web search fallback port for Corrective RAG.

Defined in ``app.rag`` so ``app.chat`` can invoke web fallback without
depending on concrete search SDKs or HTTP clients in ``app.infrastructure``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from langchain_core.documents import Document


@dataclass(frozen=True)
class WebSearchResult:
    """Normalized external web search hit."""

    title: str
    url: str
    content: str
    score: float = 0.0


@runtime_checkable
class WebSearchProvider(Protocol):
    """Protocol for optional web search fallback providers."""

    async def search(self, query: str, *, max_results: int = 3) -> list[Document]:
        """Return web results formatted as LangChain Documents."""


class NoOpWebSearchProvider:
    """Default no-op web search provider when fallback is disabled or offline."""

    async def search(self, query: str, *, max_results: int = 3) -> list[Document]:
        return []
