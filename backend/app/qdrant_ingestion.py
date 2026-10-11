"""Qdrant operations tối thiểu cho P1-05/P1-06 document lifecycle.

Module này chưa thay retrieval PostgreSQL và chưa phải vector adapter đầy đủ của M-03.
"""

from __future__ import annotations

from typing import Any, Sequence
from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)


class VectorIndexError(Exception):
    """Lỗi Qdrant an toàn, không chứa endpoint, credential hay raw response."""


class VectorCollectionMismatchError(VectorIndexError):
    pass


class QdrantIngestionIndex:
    def __init__(self, client: Any, collection_name: str):
        if client is None:
            raise VectorIndexError("Qdrant chưa kết nối")
        self._client = client
        self.collection_name = collection_name

    @staticmethod
    def _version_filter(version_id: str) -> Filter:
        return Filter(
            must=[FieldCondition(key="version_id", match=MatchValue(value=version_id))]
        )

    @staticmethod
    def _document_filter(document_id: str) -> Filter:
        return Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        )

    def ensure_collection(self, vector_size: int) -> None:
        if vector_size <= 0:
            raise VectorIndexError("Embedding dimension không hợp lệ")
        try:
            if not self._client.collection_exists(self.collection_name):
                try:
                    self._client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                    )
                except Exception:
                    # Có thể process khác vừa tạo collection; xác minh schema bên dưới.
                    if not self._client.collection_exists(self.collection_name):
                        raise

            info = self._client.get_collection(self.collection_name)
            vectors = info.config.params.vectors
            if not isinstance(vectors, VectorParams):
                raise VectorCollectionMismatchError("Collection không dùng unnamed dense vector")
            if vectors.size != vector_size or vectors.distance != Distance.COSINE:
                raise VectorCollectionMismatchError(
                    "Collection không khớp embedding dimension hoặc cosine distance"
                )
            for field_name in ("document_id", "version_id", "file_name"):
                if field_name not in info.payload_schema:
                    self._client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field_name,
                        field_schema=PayloadSchemaType.KEYWORD,
                        wait=True,
                    )
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Không thể khởi tạo hoặc xác minh Qdrant collection") from exc

    def upsert_version(
        self,
        *,
        document_id: str,
        version_id: str,
        file_name: str,
        chunks: Sequence[Document],
        vectors: Sequence[Sequence[float]],
    ) -> list[str]:
        if not chunks or len(chunks) != len(vectors):
            raise VectorIndexError("Chunks và embeddings không hợp lệ")
        vector_size = len(vectors[0])
        if vector_size <= 0 or any(len(vector) != vector_size for vector in vectors):
            raise VectorIndexError("Embedding vectors không cùng dimension")
        self.ensure_collection(vector_size)

        point_ids: list[str] = []
        points: list[PointStruct] = []
        for chunk_index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            chunk_id = str(uuid5(NAMESPACE_URL, f"{version_id}:{chunk_index}"))
            point_ids.append(chunk_id)
            points.append(
                PointStruct(
                    id=chunk_id,
                    vector=list(vector),
                    payload={
                        "document_id": document_id,
                        "version_id": version_id,
                        "chunk_id": chunk_id,
                        "chunk_index": chunk_index,
                        "file_name": file_name,
                        "page": chunk.metadata.get("page"),
                        "chunk_text": chunk.page_content,
                    },
                )
            )
        try:
            self._client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
        except Exception as exc:
            raise VectorIndexError("Không thể upsert chunks vào Qdrant") from exc
        return point_ids

    def count_version(self, version_id: str) -> int:
        try:
            if not self._client.collection_exists(self.collection_name):
                return 0
            result = self._client.count(
                collection_name=self.collection_name,
                count_filter=self._version_filter(version_id),
                exact=True,
            )
            return int(result.count)
        except Exception as exc:
            raise VectorIndexError("Không thể xác minh chunks trong Qdrant") from exc

    def delete_version(self, version_id: str) -> None:
        try:
            if not self._client.collection_exists(self.collection_name):
                return
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=self._version_filter(version_id),
                wait=True,
            )
        except Exception as exc:
            raise VectorIndexError("Không thể cleanup version trong Qdrant") from exc

    def count_document(self, document_id: str) -> int:
        try:
            if not self._client.collection_exists(self.collection_name):
                return 0
            result = self._client.count(
                collection_name=self.collection_name,
                count_filter=self._document_filter(document_id),
                exact=True,
            )
            return int(result.count)
        except Exception as exc:
            raise VectorIndexError("Không thể đếm document chunks trong Qdrant") from exc

    def delete_document(self, document_id: str) -> None:
        try:
            if not self._client.collection_exists(self.collection_name):
                return
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=self._document_filter(document_id),
                wait=True,
            )
        except Exception as exc:
            raise VectorIndexError("Không thể cleanup document trong Qdrant") from exc
