"""Orchestration cho P1-05: raw file -> Mongo lifecycle -> Qdrant index."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.shared.config import settings
from app.documents.models import (
    DocumentRecord,
    DocumentStatus,
    DocumentVersionRecord,
    IngestionJobRecord,
)
from app.documents.repository import (
    MongoDocumentRepository,
    RepositoryError,
    RepositoryNotFoundError,
)
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.rag.embeddings import get_embeddings
from app.rag.loaders.files import SUPPORTED_EXTENSIONS, load_document
from app.rag.splitter import split_documents
from app.documents.ports import FileStorage, StorageError, build_document_storage_key
from app.infrastructure.storage import create_file_storage
from app.rag.vector_index import (
    VectorFilter,
    VectorIndex,
    VectorIndexError,
    VectorRecord,
    chunk_point_id,
)


class IngestionError(Exception):
    def __init__(self, code: str, message: str = "Không thể ingest document."):
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True, slots=True)
class IngestionResult:
    document_id: str
    version_id: str
    job_id: str
    file_name: str
    num_chunks: int
    activated: bool


class IngestionService:
    def __init__(
        self,
        *,
        repository: Any,
        storage: FileStorage,
        vector_index: VectorIndex,
        embeddings: Embeddings | None = None,
        loader: Callable[[str | Path], list[Document]] = load_document,
        splitter: Callable[[list[Document]], list[Document]] = split_documents,
        embedding_model: str = settings.embedding_model,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.vector_index = vector_index
        # Khởi tạo provider lazily để list/get/delete không phụ thuộc embedding API.
        self.embeddings = embeddings
        self.loader = loader
        self.splitter = splitter
        self.embedding_model = embedding_model

    @staticmethod
    def _safe_file_name(file_name: str) -> str:
        safe_name = Path(file_name).name
        if not safe_name or safe_name != file_name:
            raise IngestionError("invalid_file_name", "Tên file không hợp lệ.")
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise IngestionError("unsupported_file_type", "Định dạng file không được hỗ trợ.")
        return safe_name

    def ingest(
        self,
        *,
        file_name: str,
        content: bytes,
        document_id: str | None = None,
        source_key: str | None = None,
    ) -> IngestionResult:
        safe_name = self._safe_file_name(file_name)
        if not content:
            raise IngestionError("empty_file", "File rỗng.")

        if document_id is None:
            document = DocumentRecord(file_name=safe_name, source_key=source_key)
            version_number = 1
        else:
            if source_key is not None:
                raise IngestionError(
                    "source_key_update_forbidden",
                    "source_key chỉ được gán khi tạo document.",
                )
            document = self.repository.get_document(document_id)
            if document.status == DocumentStatus.DELETED:
                raise IngestionError("document_deleted", "Document đã bị xóa/unpublish.")
            version_number = self.repository.next_version_number(document_id)

        version = DocumentVersionRecord(
            document_id=document.document_id,
            version=version_number,
            file_name=safe_name,
            checksum_sha256="0" * 64,
            size_bytes=0,
        )
        storage_key = build_document_storage_key(document.document_id, version.version_id)
        try:
            stored = self.storage.save(storage_key, content)
        except StorageError as exc:
            raise IngestionError("storage_failed") from exc

        version = version.model_copy(update={
            "checksum_sha256": stored.checksum_sha256,
            "size_bytes": stored.size_bytes,
            "storage_key": stored.storage_key,
        })
        job = IngestionJobRecord(document_id=document.document_id, version_id=version.version_id)
        try:
            if document_id is None:
                self.repository.create_upload(document, version, job)
            else:
                self.repository.create_version_upload(version, job)
        except Exception as exc:
            try:
                self.storage.delete(storage_key)
            except StorageError:
                pass
            if isinstance(exc, RepositoryError):
                raise IngestionError("metadata_create_failed") from exc
            raise

        return self._process(version, job)

    def retry(self, version_id: str) -> IngestionResult:
        try:
            version = self.repository.get_version(version_id)
            if version.status != DocumentStatus.FAILED:
                raise IngestionError("version_not_retryable", "Chỉ retry version FAILED.")
            if self.repository.is_active_version(version.document_id, version.version_id):
                raise IngestionError("active_version_retry_forbidden")
            job = self.repository.create_retry_job(version)
        except IngestionError:
            raise
        except RepositoryError as exc:
            raise IngestionError("metadata_read_failed") from exc
        return self._process(version, job)

    def _materialize_and_split(self, version: DocumentVersionRecord) -> list[Document]:
        if version.storage_key is None:
            raise IngestionError("missing_storage_key")
        suffix = Path(version.file_name).suffix.lower()
        try:
            with tempfile.TemporaryDirectory(prefix="rag-ingestion-") as directory:
                parse_path = Path(directory) / f"source{suffix}"
                with self.storage.open(version.storage_key) as source, parse_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
                documents = self.loader(parse_path)
                chunks = self.splitter(documents)
        except (StorageError, OSError) as exc:
            raise IngestionError("raw_file_read_failed") from exc
        except IngestionError:
            raise
        except Exception as exc:
            raise IngestionError("parse_failed") from exc
        if not chunks:
            raise IngestionError("empty_chunks")
        return chunks

    def _process(
        self,
        version: DocumentVersionRecord,
        job: IngestionJobRecord,
    ) -> IngestionResult:
        try:
            self.repository.mark_processing(version.document_id, version.version_id, job.job_id)
            chunks = self._materialize_and_split(version)
            try:
                embeddings = self.embeddings if self.embeddings is not None else get_embeddings()
                vectors = embeddings.embed_documents(
                    [chunk.page_content for chunk in chunks]
                )
            except Exception as exc:
                raise IngestionError("embedding_failed") from exc
            if len(vectors) != len(chunks) or not vectors:
                raise IngestionError("embedding_count_mismatch")

            self.repository.set_chunk_plan(
                version.version_id,
                chunk_count=len(chunks),
                embedding_model=self.embedding_model,
                vector_collection=self.vector_index.collection_name,
            )
            # Version đang xử lý chưa active; cleanup này làm retry idempotent.
            version_filter = VectorFilter(version_id=version.version_id)
            self.vector_index.delete(version_filter)
            records = [
                VectorRecord(
                    point_id=chunk_point_id(version.version_id, chunk_index),
                    document_id=version.document_id,
                    version_id=version.version_id,
                    chunk_index=chunk_index,
                    file_name=version.file_name,
                    chunk_text=chunk.page_content,
                    page=(
                        None
                        if chunk.metadata.get("page") is None
                        else int(chunk.metadata["page"])
                    ),
                    vector=tuple(vector),
                    sheet_name=chunk.metadata.get("sheet_name"),
                    row_index=chunk.metadata.get("row_index"),
                )
                for chunk_index, (chunk, vector) in enumerate(
                    zip(chunks, vectors, strict=True)
                )
            ]
            self.vector_index.upsert(records)
            actual_count = self.vector_index.count(version_filter)
            if actual_count != len(chunks):
                raise IngestionError("vector_verification_failed")
        except IngestionError as exc:
            self._fail_before_activation(version, job, exc.code)
            raise
        except VectorIndexError as exc:
            self._fail_before_activation(version, job, "vector_failed")
            raise IngestionError("vector_failed") from exc
        except RepositoryError as exc:
            self._fail_before_activation(version, job, "metadata_processing_failed")
            raise IngestionError("metadata_processing_failed") from exc
        except Exception as exc:
            self._fail_before_activation(version, job, "ingestion_failed")
            raise IngestionError("ingestion_failed") from exc

        # Từ đây vectors đã verify; nếu finalize lỗi, giữ dữ liệu cho reconciliation,
        # tuyệt đối không cleanup một version có thể đã được activate.
        try:
            activated = self.repository.complete_and_activate(version.version_id, job.job_id)
        except RepositoryError as exc:
            # DELETE/unpublish thắng race với ingestion: candidate tuyệt đối không được
            # tái xuất hiện trong retrieval sau khi document đã bị unpublish.
            try:
                deleted = self.repository.is_document_deleted(version.document_id)
            except RepositoryError:
                deleted = False
            if deleted:
                self._fail_before_activation(version, job, "document_deleted")
                raise IngestionError(
                    "document_deleted", "Document đã bị xóa/unpublish."
                ) from exc
            raise IngestionError("metadata_finalize_failed") from exc
        return IngestionResult(
            document_id=version.document_id,
            version_id=version.version_id,
            job_id=job.job_id,
            file_name=version.file_name,
            num_chunks=len(chunks),
            activated=activated,
        )

    def _fail_before_activation(
        self,
        version: DocumentVersionRecord,
        job: IngestionJobRecord,
        error_code: str,
    ) -> None:
        try:
            self.vector_index.delete(VectorFilter(version_id=version.version_id))
        except VectorIndexError:
            pass
        try:
            self.repository.mark_failed(
                version.document_id, version.version_id, job.job_id, error_code
            )
        except RepositoryError:
            pass

    def reconcile_processing(self, limit: int = 100) -> dict[str, int]:
        """Hoàn tất job bị gián đoạn sau verify, hoặc fail/cleanup version chưa đủ chunks."""
        summary = {"completed": 0, "failed": 0, "skipped": 0}
        try:
            versions = self.repository.list_processing_versions(limit=limit)
        except RepositoryError as exc:
            raise IngestionError("reconciliation_read_failed") from exc

        for version in versions:
            try:
                job = self.repository.latest_processing_job(version.version_id)
                if self.repository.is_document_deleted(version.document_id):
                    self.vector_index.delete(VectorFilter(version_id=version.version_id))
                    self.repository.mark_failed(
                        version.document_id,
                        version.version_id,
                        job.job_id,
                        "document_deleted",
                    )
                    summary["failed"] += 1
                    continue
                actual_count = self.vector_index.count(
                    VectorFilter(version_id=version.version_id)
                )
                if actual_count == version.chunk_count and actual_count > 0:
                    self.repository.complete_and_activate(version.version_id, job.job_id)
                    summary["completed"] += 1
                elif self.repository.is_active_version(version.document_id, version.version_id):
                    summary["skipped"] += 1
                else:
                    self.vector_index.delete(VectorFilter(version_id=version.version_id))
                    self.repository.mark_failed(
                        version.document_id,
                        version.version_id,
                        job.job_id,
                        "reconciliation_count_mismatch",
                    )
                    summary["failed"] += 1
            except (RepositoryError, RepositoryNotFoundError, VectorIndexError):
                summary["skipped"] += 1
        return summary


def create_ingestion_service(
    *,
    database: Any,
    qdrant_client: Any,
    embeddings: Embeddings | None = None,
    storage: FileStorage | None = None,
) -> IngestionService:
    """Composition root nhỏ cho API/script; tests có thể inject toàn bộ adapters."""
    return IngestionService(
        repository=MongoDocumentRepository(database),
        storage=storage if storage is not None else create_file_storage(settings),
        vector_index=QdrantVectorIndex(qdrant_client, settings.qdrant_collection),
        embeddings=embeddings,
        embedding_model=settings.embedding_model,
    )
