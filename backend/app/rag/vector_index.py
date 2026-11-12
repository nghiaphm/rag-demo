"""Backend-neutral contract cho vector index và các value object đã validation."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5


class VectorIndexError(Exception):
    """Lỗi vector backend an toàn, không chứa endpoint, credential hay raw response."""


class VectorConflictError(VectorIndexError):
    pass


class VectorCollectionMismatchError(VectorIndexError):
    pass


def canonical_uuid(value: str, field_name: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} phải là UUID hợp lệ") from exc


def chunk_point_id(version_id: str, chunk_index: int) -> str:
    canonical_version = canonical_uuid(version_id, "version_id")
    if chunk_index < 0:
        raise ValueError("chunk_index không được âm")
    return str(uuid5(NAMESPACE_URL, f"{canonical_version}:{chunk_index}"))


@dataclass(frozen=True, slots=True)
class VectorRecord:
    point_id: str
    document_id: str
    version_id: str
    chunk_index: int
    file_name: str
    chunk_text: str
    vector: tuple[float, ...]
    page: int | None = None
    sheet_name: str | None = None
    row_index: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "point_id", canonical_uuid(self.point_id, "point_id"))
        object.__setattr__(self, "document_id", canonical_uuid(self.document_id, "document_id"))
        object.__setattr__(self, "version_id", canonical_uuid(self.version_id, "version_id"))
        if self.chunk_index < 0:
            raise ValueError("chunk_index không được âm")
        if not self.file_name.strip():
            raise ValueError("file_name không được rỗng")
        if not self.chunk_text.strip():
            raise ValueError("chunk_text không được rỗng")
        normalized = tuple(float(value) for value in self.vector)
        if not normalized or any(not math.isfinite(value) for value in normalized):
            raise ValueError("vector phải có giá trị hữu hạn và không rỗng")
        object.__setattr__(self, "vector", normalized)
        if self.page is not None and self.page < 0:
            raise ValueError("page không được âm")

    def payload(self) -> dict[str, str | int | None]:
        return {
            "document_id": self.document_id,
            "version_id": self.version_id,
            "chunk_id": self.point_id,
            "chunk_index": self.chunk_index,
            "file_name": self.file_name,
            "page": self.page,
            "chunk_text": self.chunk_text,
            **({"sheet_name": self.sheet_name, "row_index": self.row_index} if self.sheet_name is not None else {}),
        }


@dataclass(frozen=True, slots=True)
class VectorFilter:
    document_id: str | None = None
    version_id: str | None = None
    version_ids: tuple[str, ...] | None = None
    file_name: str | None = None

    def __post_init__(self) -> None:
        if self.document_id is not None:
            object.__setattr__(
                self, "document_id", canonical_uuid(self.document_id, "document_id")
            )
        if self.version_id is not None:
            object.__setattr__(
                self, "version_id", canonical_uuid(self.version_id, "version_id")
            )
        if self.version_ids is not None:
            normalized = tuple(
                canonical_uuid(value, "version_ids") for value in self.version_ids
            )
            if not normalized:
                raise ValueError("version_ids không được rỗng")
            if len(set(normalized)) != len(normalized):
                raise ValueError("version_ids không được trùng")
            object.__setattr__(self, "version_ids", normalized)
        if self.version_id is not None and self.version_ids is not None:
            raise ValueError("Không dùng đồng thời version_id và version_ids")
        if self.file_name is not None and not self.file_name.strip():
            raise ValueError("file_name filter không được rỗng")

    @property
    def is_empty(self) -> bool:
        return (
            self.document_id is None
            and self.version_id is None
            and self.version_ids is None
            and self.file_name is None
        )


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    point_id: str
    document_id: str
    version_id: str
    chunk_index: int
    file_name: str
    chunk_text: str
    score: float
    page: int | None = None
    sheet_name: str | None = None
    row_index: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "point_id", canonical_uuid(self.point_id, "point_id"))
        object.__setattr__(self, "document_id", canonical_uuid(self.document_id, "document_id"))
        object.__setattr__(self, "version_id", canonical_uuid(self.version_id, "version_id"))
        if self.chunk_index < 0:
            raise ValueError("chunk_index không được âm")
        if not self.file_name.strip() or not self.chunk_text.strip():
            raise ValueError("Kết quả query thiếu file_name hoặc chunk_text")
        if not math.isfinite(self.score):
            raise ValueError("score phải hữu hạn")
        if self.page is not None and self.page < 0:
            raise ValueError("page không được âm")


class VectorIndex(ABC):
    """Contract dùng bởi business logic; adapter cụ thể chịu trách nhiệm mapping backend."""

    @property
    @abstractmethod
    def collection_name(self) -> str: ...

    @abstractmethod
    def ensure_collection(self, vector_size: int) -> None: ...

    @abstractmethod
    def add(self, records: list[VectorRecord]) -> None: ...

    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None: ...

    @abstractmethod
    def query(
        self,
        query_vector: list[float] | tuple[float, ...],
        *,
        limit: int,
        filters: VectorFilter | None = None,
    ) -> list[VectorSearchResult]: ...

    def query_hybrid(
        self,
        query_text: str,
        query_vector: list[float] | tuple[float, ...] | None = None,
        *,
        limit: int,
        filters: VectorFilter | None = None,
        rrf_k: int = 60,
    ) -> list[VectorSearchResult]:
        """Hybrid search combining keyword match and dense vector search with RRF."""
        if query_vector is not None:
            return self.query(query_vector, limit=limit, filters=filters)
        return []

    @abstractmethod
    def count(self, filters: VectorFilter) -> int: ...

    @abstractmethod
    def delete(self, filters: VectorFilter) -> None: ...
