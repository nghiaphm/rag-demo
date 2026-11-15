"""Concrete web search fallback adapter (Tavily HTTP API + NoOp fallback)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.documents import Document

from app.rag.web_search import NoOpWebSearchProvider, WebSearchProvider
from app.shared.config import Settings, get_settings

logger = logging.getLogger(__name__)


class TavilyWebSearchProvider:
    """Tavily Search API adapter returning Documents tagged as web fallback."""

    def __init__(self, *, api_key: str, timeout_seconds: float = 8.0) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def search(self, query: str, *, max_results: int = 3) -> list[Document]:
        if not query or not query.strip():
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self._api_key,
                        "query": query.strip(),
                        "max_results": max(1, min(max_results, 5)),
                        "search_depth": "basic",
                    },
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
        except Exception as exc:
            logger.warning("Tavily web search fallback failed: %s", exc)
            return []

        documents: list[Document] = []
        for idx, item in enumerate(payload.get("results", [])[:max_results], start=1):
            content = str(item.get("content") or "").strip()
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or url or f"Web Result {idx}").strip()
            if not content:
                continue
            documents.append(
                Document(
                    page_content=content,
                    metadata={
                        "source_type": "web_fallback",
                        "file_name": title,
                        "url": url,
                        "chunk_index": idx,
                        "score": item.get("score", 0.0),
                    },
                )
            )
        return documents


def get_web_search_provider(settings: Settings | None = None) -> WebSearchProvider:
    """Return TavilyWebSearchProvider if enabled and configured, otherwise NoOp."""
    cfg = settings or get_settings()
    if not cfg.web_search_fallback_enabled:
        return NoOpWebSearchProvider()

    api_key = cfg.tavily_api_key.get_secret_value() if cfg.tavily_api_key else None
    if not api_key:
        logger.warning("WEB_SEARCH_FALLBACK_ENABLED is true but TAVILY_API_KEY is missing; using NoOp.")
        return NoOpWebSearchProvider()

    return TavilyWebSearchProvider(api_key=api_key)
