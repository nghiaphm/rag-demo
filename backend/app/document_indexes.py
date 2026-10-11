"""Index specifications và initializer idempotent cho document collections."""

from collections.abc import Mapping, Sequence
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel

DOCUMENTS_COLLECTION = "documents"
DOCUMENT_VERSIONS_COLLECTION = "document_versions"
INGESTION_JOBS_COLLECTION = "ingestion_jobs"

DOCUMENT_INDEXES: tuple[IndexModel, ...] = (
    IndexModel([("file_name", ASCENDING)], name="idx_documents_file_name"),
    IndexModel(
        [("status", ASCENDING), ("updated_at", DESCENDING)],
        name="idx_documents_status_updated_at",
    ),
    IndexModel(
        [("active_version_id", ASCENDING)],
        name="idx_documents_active_version_id",
        sparse=True,
    ),
)

DOCUMENT_VERSION_INDEXES: tuple[IndexModel, ...] = (
    IndexModel(
        [("document_id", ASCENDING), ("version", ASCENDING)],
        name="uq_document_versions_document_version",
        unique=True,
    ),
    IndexModel(
        [("document_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_document_versions_document_created_at",
    ),
    IndexModel(
        [("checksum_sha256", ASCENDING)],
        name="idx_document_versions_checksum",
    ),
    IndexModel(
        [("status", ASCENDING), ("updated_at", DESCENDING)],
        name="idx_document_versions_status_updated_at",
    ),
)

INGESTION_JOB_INDEXES: tuple[IndexModel, ...] = (
    IndexModel(
        [("status", ASCENDING), ("created_at", ASCENDING)],
        name="idx_ingestion_jobs_status_created_at",
    ),
    IndexModel(
        [("document_id", ASCENDING), ("version_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_ingestion_jobs_document_version_created_at",
    ),
)

INDEX_DEFINITIONS: Mapping[str, Sequence[IndexModel]] = {
    DOCUMENTS_COLLECTION: DOCUMENT_INDEXES,
    DOCUMENT_VERSIONS_COLLECTION: DOCUMENT_VERSION_INDEXES,
    INGESTION_JOBS_COLLECTION: INGESTION_JOB_INDEXES,
}


def initialize_document_indexes(database: Any) -> dict[str, list[str]]:
    """Tạo indexes có tên cố định; gọi lại an toàn khi spec không thay đổi."""
    return {
        collection_name: database[collection_name].create_indexes(list(indexes))
        for collection_name, indexes in INDEX_DEFINITIONS.items()
    }
