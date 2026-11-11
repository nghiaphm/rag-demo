"""Business service cho document management API trên MongoDB/Qdrant/local storage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.shared.config import settings
from app.documents.models import DocumentRecord, DocumentStatus, DocumentVersionRecord
from app.documents.repository import MongoDocumentRepository
from app.documents.ingestion import (
    IngestionError,
    IngestionResult,
    IngestionService,
)
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.documents.ports import FileStorage, StorageError
from app.infrastructure.storage import create_file_storage
from app.rag.vector_index import VectorFilter, VectorIndex, VectorIndexError


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    document: DocumentRecord
    active_version: DocumentVersionRecord | None
    version_count: int


@dataclass(frozen=True, slots=True)
class DocumentDetail:
    document: DocumentRecord
    versions: list[DocumentVersionRecord]


@dataclass(frozen=True, slots=True)
class DeleteResult:
    document_id: str
    deleted_chunks: int
    retained_files: int
    cleanup_pending: bool


class DocumentService:
    def __init__(
        self,
        *,
        repository: Any,
        storage: FileStorage,
        vector_index: VectorIndex,
        ingestion: IngestionService,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.vector_index = vector_index
        self.ingestion = ingestion

    def list_documents(
        self, *, include_deleted: bool = False, offset: int = 0, limit: int = 100
    ) -> list[DocumentSummary]:
        summaries: list[DocumentSummary] = []
        for document in self.repository.list_documents(
            include_deleted=include_deleted, offset=offset, limit=limit
        ):
            versions = self.repository.list_versions(document.document_id)
            active = next(
                (item for item in versions if item.version_id == document.active_version_id),
                None,
            )
            summaries.append(
                DocumentSummary(
                    document=document,
                    active_version=active,
                    version_count=len(versions),
                )
            )
        return summaries

    def get_document(self, document_id: str) -> DocumentDetail:
        document = self.repository.get_document(document_id)
        return DocumentDetail(
            document=document,
            versions=self.repository.list_versions(document_id),
        )

    def update(self, document_id: str, *, file_name: str, content: bytes) -> IngestionResult:
        return self.ingestion.ingest(
            document_id=document_id, file_name=file_name, content=content
        )

    def reindex(self, document_id: str) -> IngestionResult:
        document = self.repository.get_document(document_id)
        if document.status == DocumentStatus.DELETED:
            raise IngestionError("document_deleted", "Document đã bị xóa/unpublish.")
        if document.active_version_id is None:
            raise IngestionError("active_version_missing", "Document chưa có active version.")
        active = self.repository.get_version(document.active_version_id)
        if active.storage_key is None:
            raise IngestionError("missing_storage_key", "Active version không có raw file.")
        try:
            content = self.storage.read(active.storage_key)
        except StorageError as exc:
            raise IngestionError("raw_file_read_failed", "Không thể đọc raw file.") from exc
        return self.update(document_id, file_name=active.file_name, content=content)

    def delete(self, document_id: str) -> DeleteResult:
        # Unpublish metadata trước để retrieval về sau không được coi document là active,
        # kể cả khi Qdrant đang lỗi. Raw files và audit history được giữ lại theo policy.
        versions = self.repository.list_versions(document_id)
        self.repository.unpublish(document_id)
        retained_files = sum(1 for version in versions if version.storage_key is not None)
        deleted_chunks = 0
        cleanup_pending = True
        try:
            document_filter = VectorFilter(document_id=document_id)
            deleted_chunks = self.vector_index.count(document_filter)
            self.vector_index.delete(document_filter)
            if self.vector_index.count(document_filter) != 0:
                raise VectorIndexError("Qdrant vẫn còn points sau cleanup")
            self.repository.mark_cleanup_complete(document_id)
            cleanup_pending = False
        except VectorIndexError:
            # Idempotent DELETE có thể được gọi lại để retry cleanup.
            cleanup_pending = True
        return DeleteResult(
            document_id=document_id,
            deleted_chunks=deleted_chunks,
            retained_files=retained_files,
            cleanup_pending=cleanup_pending,
        )


def create_document_service(*, database: Any, qdrant_client: Any) -> DocumentService:
    repository = MongoDocumentRepository(database)
    storage = create_file_storage(settings)
    vector_index = QdrantVectorIndex(qdrant_client, settings.qdrant_collection)
    ingestion = IngestionService(
        repository=repository,
        storage=storage,
        vector_index=vector_index,
        embedding_model=settings.embedding_model,
    )
    return DocumentService(
        repository=repository,
        storage=storage,
        vector_index=vector_index,
        ingestion=ingestion,
    )
