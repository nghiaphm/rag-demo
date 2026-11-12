"""LangChain retriever backed by Qdrant and MongoDB active-version scope."""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from app.shared.config import settings
from app.rag.embeddings import get_embeddings
from app.rag.vector_index import VectorFilter, VectorIndex


class QdrantActiveVersionRetriever(BaseRetriever):
    """Retrieve only points whose version is currently active in MongoDB."""

    vector_index: Any
    embeddings: Any
    repository: Any | None = None
    active_version_ids: tuple[str, ...] | None = None
    top_k: int = 5

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _allowed_versions(self) -> tuple[str, ...]:
        if self.active_version_ids is not None:
            return self.active_version_ids
        if self.repository is None:
            raise ValueError("Retriever thiếu active-version source")
        return tuple(self.repository.list_active_version_ids())

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        version_ids = self._allowed_versions()
        if not version_ids:
            return []
        results = self.vector_index.query(
            self.embeddings.embed_query(query),
            limit=self.top_k,
            filters=VectorFilter(version_ids=version_ids),
        )
        return [
            Document(
                page_content=result.chunk_text,
                metadata={
                    "source": result.file_name,
                    "file_name": result.file_name,
                    "document_id": result.document_id,
                    "version_id": result.version_id,
                    "chunk_id": result.point_id,
                    "chunk_index": result.chunk_index,
                    "page": result.page,
                    "score": result.score,
                    **({"sheet_name": result.sheet_name, "row_index": result.row_index} if result.sheet_name is not None else {}),
                },
            )
            for result in results
        ]


def get_retriever(
    *,
    database: Any | None = None,
    qdrant_client: Any | None = None,
    embeddings: Embeddings | None = None,
    vector_index: VectorIndex | None = None,
    repository: Any | None = None,
    active_version_ids: tuple[str, ...] | None = None,
    collection_name: str | None = None,
    top_k: int | None = None,
) -> BaseRetriever:
    """Compose the production or isolated-evaluation Qdrant retriever."""
    resolved_index = vector_index
    if resolved_index is None:
        if qdrant_client is None:
            raise ValueError("Qdrant client chưa sẵn sàng")
        from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
        resolved_index = QdrantVectorIndex(
            qdrant_client,
            collection_name or settings.qdrant_collection,
        )
    resolved_repository = repository
    if resolved_repository is None and active_version_ids is None:
        if database is None:
            raise ValueError("MongoDB database chưa sẵn sàng")
        from app.documents.repository import MongoDocumentRepository
        resolved_repository = MongoDocumentRepository(database)
    return QdrantActiveVersionRetriever(
        vector_index=resolved_index,
        embeddings=embeddings if embeddings is not None else get_embeddings(),
        repository=resolved_repository,
        active_version_ids=active_version_ids,
        top_k=top_k if top_k is not None else (
            settings.reranker_candidate_top_k if getattr(settings, "reranker_enabled", False) else settings.top_k
        ),
    )
