"""Idempotent migration of the repository-owned demo corpus into V2 storage."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from langchain_core.embeddings import Embeddings

from app.document_models import DocumentStatus
from app.document_repository import RepositoryError
from app.ingestion import IngestionError, IngestionService
from app.storage import FileStorage, StorageError
from app.vector_index import VectorFilter, VectorIndex, VectorIndexError


class DataMigrationError(Exception):
    def __init__(self, code: str, message: str = "Data migration failed."):
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True, slots=True)
class MigrationSource:
    source_key: str
    path: Path

    def __post_init__(self) -> None:
        if not self.source_key.strip() or len(self.source_key) > 512:
            raise ValueError("source_key không hợp lệ")


@dataclass(frozen=True, slots=True)
class MigrationItemResult:
    source_key: str
    file_name: str
    outcome: str
    document_id: str | None
    version_id: str | None
    chunk_count: int
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class MigrationSummary:
    items: tuple[MigrationItemResult, ...]

    @property
    def created(self) -> int:
        return sum(item.outcome == "CREATED" for item in self.items)

    @property
    def updated(self) -> int:
        return sum(item.outcome == "UPDATED" for item in self.items)

    @property
    def verified(self) -> int:
        return sum(item.outcome == "VERIFIED" for item in self.items)

    @property
    def failed(self) -> int:
        return sum(item.outcome == "FAILED" for item in self.items)


class DemoCorpusMigration:
    """Migrate only explicitly supplied sources; never scans runtime storage."""

    def __init__(
        self,
        *,
        repository: Any,
        storage: FileStorage,
        vector_index: VectorIndex,
        ingestion: IngestionService,
        embeddings: Embeddings,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.vector_index = vector_index
        self.ingestion = ingestion
        self.embeddings = embeddings

    @staticmethod
    def _checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _verify(self, document_id: str, expected_checksum: str) -> tuple[str, int]:
        document = self.repository.get_document(document_id)
        if document.status != DocumentStatus.INDEXED or document.active_version_id is None:
            raise DataMigrationError("document_not_indexed")
        version = self.repository.get_version(document.active_version_id)
        if version.status != DocumentStatus.INDEXED:
            raise DataMigrationError("version_not_indexed")
        if version.checksum_sha256 != expected_checksum:
            raise DataMigrationError("checksum_mismatch")
        if version.storage_key is None:
            raise DataMigrationError("missing_storage_key")
        try:
            stored = self.storage.read(version.storage_key)
        except StorageError as exc:
            raise DataMigrationError("raw_file_unavailable") from exc
        if self._checksum(stored) != expected_checksum or len(stored) != version.size_bytes:
            raise DataMigrationError("raw_file_mismatch")

        filters = VectorFilter(document_id=document_id, version_id=version.version_id)
        try:
            count = self.vector_index.count(filters)
            if count <= 0 or count != version.chunk_count:
                raise DataMigrationError("vector_count_mismatch")
            query_vector = self.embeddings.embed_query(
                f"Verify migrated document {version.file_name}"
            )
            hits = self.vector_index.query(query_vector, limit=1, filters=filters)
        except DataMigrationError:
            raise
        except VectorIndexError as exc:
            raise DataMigrationError("vector_verification_failed") from exc
        except Exception as exc:
            raise DataMigrationError("embedding_verification_failed") from exc
        if not hits:
            raise DataMigrationError("retrieval_verification_failed")
        hit = hits[0]
        if (
            hit.document_id != document_id
            or hit.version_id != version.version_id
            or not hit.chunk_text.strip()
        ):
            raise DataMigrationError("retrieval_metadata_mismatch")
        return version.version_id, count

    def migrate(self, sources: Iterable[MigrationSource]) -> MigrationSummary:
        results: list[MigrationItemResult] = []
        seen: set[str] = set()
        for source in sources:
            if source.source_key in seen:
                raise DataMigrationError("duplicate_source_key")
            seen.add(source.source_key)
            file_name = source.path.name
            document_id: str | None = None
            try:
                content = source.path.read_bytes()
                if not content:
                    raise DataMigrationError("empty_source")
                checksum = self._checksum(content)
                document = self.repository.find_document_by_source_key(source.source_key)
                if document is not None:
                    document_id = document.document_id
                    if document.status == DocumentStatus.DELETED:
                        raise DataMigrationError("source_document_deleted")
                    if document.active_version_id is not None:
                        active = self.repository.get_version(document.active_version_id)
                        if active.checksum_sha256 == checksum:
                            # Same source bytes must be a read-only/idempotent path. A
                            # transient verification error is reported, never converted
                            # into an unnecessary immutable version.
                            version_id, count = self._verify(document_id, checksum)
                            results.append(MigrationItemResult(
                                source.source_key, file_name, "VERIFIED",
                                document_id, version_id, count,
                            ))
                            continue
                    ingestion_result = self.ingestion.ingest(
                        file_name=file_name, content=content, document_id=document_id
                    )
                    outcome = "UPDATED"
                else:
                    ingestion_result = self.ingestion.ingest(
                        file_name=file_name,
                        content=content,
                        source_key=source.source_key,
                    )
                    document_id = ingestion_result.document_id
                    outcome = "CREATED"
                version_id, count = self._verify(document_id, checksum)
                if version_id != ingestion_result.version_id or not ingestion_result.activated:
                    raise DataMigrationError("activation_verification_failed")
                results.append(MigrationItemResult(
                    source.source_key, file_name, outcome,
                    document_id, version_id, count,
                ))
            except (OSError, RepositoryError, IngestionError, DataMigrationError) as exc:
                code = getattr(exc, "code", None) or (
                    "source_read_failed" if isinstance(exc, OSError) else "migration_failed"
                )
                results.append(MigrationItemResult(
                    source.source_key, file_name, "FAILED",
                    document_id, None, 0, str(code),
                ))
        return MigrationSummary(tuple(results))
