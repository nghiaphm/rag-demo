"""Qdrant Cloud adapter cho backend-neutral :mod:`app.vector_index` contract."""

from __future__ import annotations

import math
from typing import Any, Sequence

from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.vector_index import (
    VectorCollectionMismatchError,
    VectorConflictError,
    VectorFilter,
    VectorIndex,
    VectorIndexError,
    VectorRecord,
    VectorSearchResult,
)


class QdrantVectorIndex(VectorIndex):
    def __init__(self, client: Any, collection_name: str):
        if client is None:
            raise VectorIndexError("Qdrant chưa kết nối")
        self._client = client
        self._collection_name = collection_name

    @property
    def collection_name(self) -> str:
        return self._collection_name

    @staticmethod
    def _to_qdrant_filter(filters: VectorFilter | None) -> Filter | None:
        if filters is None or filters.is_empty:
            return None
        values = (
            ("document_id", filters.document_id),
            ("version_id", filters.version_id),
            ("file_name", filters.file_name),
        )
        must = [
            FieldCondition(key=key, match=MatchValue(value=value))
            for key, value in values
            if value is not None
        ]
        if filters.version_ids is not None:
            must.append(
                FieldCondition(
                    key="version_id",
                    match=MatchAny(any=list(filters.version_ids)),
                )
            )
        return Filter(must=must)

    @staticmethod
    def _validate_records(records: Sequence[VectorRecord]) -> int:
        if not records:
            raise VectorIndexError("Danh sách vector records không được rỗng")
        vector_size = len(records[0].vector)
        if vector_size <= 0 or any(len(record.vector) != vector_size for record in records):
            raise VectorIndexError("Embedding vectors không cùng dimension")
        point_ids = [record.point_id for record in records]
        if len(set(point_ids)) != len(point_ids):
            raise VectorConflictError("Point ID bị trùng trong request")
        return vector_size

    @staticmethod
    def _points(records: Sequence[VectorRecord]) -> list[PointStruct]:
        return [
            PointStruct(
                id=record.point_id,
                vector=list(record.vector),
                payload=record.payload(),
            )
            for record in records
        ]

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

    def add(self, records: list[VectorRecord]) -> None:
        vector_size = self._validate_records(records)
        self.ensure_collection(vector_size)
        try:
            existing = self._client.retrieve(
                collection_name=self.collection_name,
                ids=[record.point_id for record in records],
                with_payload=False,
                with_vectors=False,
            )
            if existing:
                raise VectorConflictError("Một hoặc nhiều point ID đã tồn tại")
            self._client.upsert(
                collection_name=self.collection_name,
                points=self._points(records),
                wait=True,
            )
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Không thể add vectors vào Qdrant") from exc

    def upsert(self, records: list[VectorRecord]) -> None:
        vector_size = self._validate_records(records)
        self.ensure_collection(vector_size)
        try:
            self._client.upsert(
                collection_name=self.collection_name,
                points=self._points(records),
                wait=True,
            )
        except Exception as exc:
            raise VectorIndexError("Không thể upsert vectors vào Qdrant") from exc

    def query(
        self,
        query_vector: list[float] | tuple[float, ...],
        *,
        limit: int,
        filters: VectorFilter | None = None,
    ) -> list[VectorSearchResult]:
        vector = [float(value) for value in query_vector]
        if not vector or any(not math.isfinite(value) for value in vector):
            raise ValueError("query_vector phải có giá trị hữu hạn và không rỗng")
        if limit <= 0:
            raise ValueError("limit phải lớn hơn 0")
        try:
            if not self._client.collection_exists(self.collection_name):
                return []
            response = self._client.query_points(
                collection_name=self.collection_name,
                query=vector,
                query_filter=self._to_qdrant_filter(filters),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            results: list[VectorSearchResult] = []
            for point in response.points:
                payload = point.payload or {}
                try:
                    results.append(
                        VectorSearchResult(
                            point_id=str(point.id),
                            document_id=str(payload["document_id"]),
                            version_id=str(payload["version_id"]),
                            chunk_index=int(payload["chunk_index"]),
                            file_name=str(payload["file_name"]),
                            chunk_text=str(payload["chunk_text"]),
                            page=None if payload.get("page") is None else int(payload["page"]),
                            score=float(point.score),
                            sheet_name=payload.get("sheet_name"),
                            row_index=payload.get("row_index"),
                        )
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise VectorIndexError("Qdrant point thiếu payload bắt buộc") from exc
            return results
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Không thể query vectors từ Qdrant") from exc

    def count(self, filters: VectorFilter) -> int:
        try:
            if not self._client.collection_exists(self.collection_name):
                return 0
            result = self._client.count(
                collection_name=self.collection_name,
                count_filter=self._to_qdrant_filter(filters),
                exact=True,
            )
            return int(result.count)
        except Exception as exc:
            raise VectorIndexError("Không thể đếm vectors trong Qdrant") from exc

    def delete(self, filters: VectorFilter) -> None:
        if filters.is_empty:
            raise ValueError("Từ chối delete không có filter")
        try:
            if not self._client.collection_exists(self.collection_name):
                return
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=self._to_qdrant_filter(filters),
                wait=True,
            )
        except Exception as exc:
            raise VectorIndexError("Không thể delete vectors khỏi Qdrant") from exc

__all__ = [
    "QdrantVectorIndex",
    "VectorCollectionMismatchError",
    "VectorConflictError",
    "VectorIndexError",
]
