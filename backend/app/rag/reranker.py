"""Reranker interface and implementations (FlashRank, Cohere, PassThrough) for Advanced RAG."""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


@runtime_checkable
class RerankerPort(Protocol):
    """Abstract contract for document re-ranking."""

    def rerank(
        self,
        query: str,
        documents: list[Document],
        *,
        top_k: int | None = None,
        relevance_threshold: float | None = None,
    ) -> list[Document]:
        """Rerank candidate documents based on cross-encoder query-document relevance."""
        ...


class PassThroughReranker:
    """No-op reranker returning documents in original retrieval order up to top_k."""

    def rerank(
        self,
        query: str,
        documents: list[Document],
        *,
        top_k: int | None = None,
        relevance_threshold: float | None = None,
    ) -> list[Document]:
        limit = top_k if top_k is not None else len(documents)
        return documents[:limit]


class FlashRankReranker:
    """Ultra-lightweight local/offline cross-encoder reranker using FlashRank (ONNX runtime)."""

    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2", ranker: Any | None = None) -> None:
        self.model_name = model_name
        self._ranker = ranker

    def _get_ranker(self) -> Any | None:
        if self._ranker is None:
            try:
                from flashrank import Ranker
                self._ranker = Ranker(model_name=self.model_name)
            except Exception as exc:
                logger.warning(
                    "Không thể khởi tạo FlashRank model %s: %s. Fallback về PassThrough.",
                    self.model_name,
                    exc,
                )
                return None
        return self._ranker

    def rerank(
        self,
        query: str,
        documents: list[Document],
        *,
        top_k: int | None = None,
        relevance_threshold: float | None = None,
    ) -> list[Document]:
        if not documents:
            return []

        ranker = self._get_ranker()
        if ranker is None:
            limit = top_k if top_k is not None else len(documents)
            return documents[:limit]

        from flashrank import RerankRequest

        passages = []
        for idx, doc in enumerate(documents):
            passages.append({
                "id": doc.metadata.get("chunk_id", str(idx)),
                "text": doc.page_content,
                "meta": {"doc_idx": idx},
            })

        request = RerankRequest(query=query, passages=passages)
        ranked_results = ranker.rerank(request)

        threshold = relevance_threshold if relevance_threshold is not None else 0.0
        reranked_docs: list[Document] = []
        for res in ranked_results:
            score = float(res.get("score", 0.0))
            if score < threshold:
                continue
            original_idx = res["meta"]["doc_idx"]
            orig_doc = documents[original_idx]
            new_metadata = dict(orig_doc.metadata)
            new_metadata["rerank_score"] = score
            reranked_docs.append(Document(
                page_content=orig_doc.page_content,
                metadata=new_metadata,
            ))

        limit = top_k if top_k is not None else len(reranked_docs)
        return reranked_docs[:limit]


class CohereReranker:
    """Cloud-based cross-encoder reranker using Cohere Rerank API."""

    def __init__(self, api_key: str | None = None, model: str = "rerank-v3.5") -> None:
        self.api_key = api_key
        self.model = model
        self._client: Any | None = None

    def _get_client(self) -> Any | None:
        if self._client is None:
            try:
                import cohere
                from app.shared.config import settings

                key = self.api_key or (settings.cohere_api_key.get_secret_value() if settings.cohere_api_key else None)
                if not key:
                    logger.warning("COHERE_API_KEY chưa được cấu hình. Fallback về PassThrough.")
                    return None
                self._client = cohere.ClientV2(api_key=key)
            except Exception as exc:
                logger.warning("Không thể khởi tạo Cohere client: %s. Fallback về PassThrough.", exc)
                return None
        return self._client

    def rerank(
        self,
        query: str,
        documents: list[Document],
        *,
        top_k: int | None = None,
        relevance_threshold: float | None = None,
    ) -> list[Document]:
        if not documents:
            return []

        client = self._get_client()
        if client is None:
            limit = top_k if top_k is not None else len(documents)
            return documents[:limit]

        try:
            texts = [doc.page_content for doc in documents]
            response = client.rerank(
                model=self.model,
                query=query,
                documents=texts,
                top_n=top_k or len(documents),
            )
            threshold = relevance_threshold if relevance_threshold is not None else 0.0
            reranked: list[Document] = []
            for item in response.results:
                score = float(item.relevance_score)
                if score < threshold:
                    continue
                orig_doc = documents[item.index]
                new_metadata = dict(orig_doc.metadata)
                new_metadata["rerank_score"] = score
                reranked.append(Document(
                    page_content=orig_doc.page_content,
                    metadata=new_metadata,
                ))
            return reranked
        except Exception as exc:
            logger.warning("Cohere rerank thất bại: %s. Giữ thứ tự ban đầu.", exc)
            limit = top_k if top_k is not None else len(documents)
            return documents[:limit]


def get_reranker(
    *,
    enabled: bool | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> RerankerPort:
    """Factory creating configured reranker instance with safe fallbacks."""
    from app.shared.config import settings

    is_enabled = enabled if enabled is not None else getattr(settings, "reranker_enabled", False)
    if not is_enabled:
        return PassThroughReranker()

    chosen_provider = (provider or getattr(settings, "reranker_provider", "flashrank")).strip().lower()
    if chosen_provider == "flashrank":
        chosen_model = model or getattr(settings, "reranker_model", "ms-marco-TinyBERT-L-2-v2")
        return FlashRankReranker(model_name=chosen_model)
    elif chosen_provider == "cohere":
        return CohereReranker()

    return PassThroughReranker()
