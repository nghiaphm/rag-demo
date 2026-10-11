"""Live P1-05 smoke với namespace riêng và cleanup chính xác, không xóa collection."""

import sys
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.cloud_connections import CloudConnections
from app.document_indexes import (
    DOCUMENTS_COLLECTION,
    DOCUMENT_VERSIONS_COLLECTION,
    INGESTION_JOBS_COLLECTION,
    initialize_document_indexes,
)
from app.document_models import DocumentStatus, IngestionJobStatus
from app.ingestion import create_ingestion_service
from app.qdrant_ingestion import QdrantIngestionIndex, VectorIndexError
from app.storage import StorageError, create_file_storage
from app.config import settings


def main() -> int:
    marker = f"p1-05-smoke-{uuid4()}.md"
    connections = CloudConnections()
    statuses = connections.connect_all()
    database = connections.mongodb.database
    vector_index = None
    storage = None
    cleanup_ok = True
    stage = "connect"
    try:
        if not all(status.ok for status in statuses.values()):
            codes = ", ".join(f"{name}={status.code}" for name, status in statuses.items())
            print(f"BLOCKED: cloud dependencies chưa sẵn sàng ({codes}); credentials không được in.")
            return 2
        stage = "indexes"
        initialize_document_indexes(database)
        stage = "storage"
        storage = create_file_storage(settings)
        stage = "service"
        vector_index = QdrantIngestionIndex(
            connections.qdrant.client, settings.qdrant_collection
        )
        service = create_ingestion_service(
            database=database,
            qdrant_client=connections.qdrant.client,
            storage=storage,
        )
        stage = "ingest"
        result = service.ingest(
            file_name=marker,
            content=b"# P1-05 smoke\n\nNon-sensitive integration test content.",
        )
        stage = "verify"
        document = database[DOCUMENTS_COLLECTION].find_one({"_id": result.document_id})
        version = database[DOCUMENT_VERSIONS_COLLECTION].find_one({"_id": result.version_id})
        job = database[INGESTION_JOBS_COLLECTION].find_one({"_id": result.job_id})
        checks = {
            "document_indexed": document is not None
            and document.get("status") == DocumentStatus.INDEXED.value
            and document.get("active_version_id") == result.version_id,
            "version_indexed": version is not None
            and version.get("status") == DocumentStatus.INDEXED.value,
            "job_completed": job is not None
            and job.get("status") == IngestionJobStatus.COMPLETED.value,
            "raw_file_exists": version is not None
            and storage.exists(version["storage_key"]),
            "qdrant_verified": vector_index.count_version(result.version_id)
            == result.num_chunks,
        }
        if not all(checks.values()):
            print("FAILED: live ingestion verification mismatch.")
            return 1
        print(f"PASS: live ingestion verified ({result.num_chunks} chunk).")
        return 0
    except ValidationError as exc:
        fields = ",".join(
            ".".join(str(part) for part in item["loc"]) + ":" + item["type"]
            for item in exc.errors(include_input=False, include_url=False)
        )
        print(f"FAILED: stage={stage}; type=ValidationError; fields={fields}")
        return 1
    except Exception as exc:
        print(
            f"FAILED: stage={stage}; type={type(exc).__name__}; "
            "secrets/raw exception không được in."
        )
        return 1
    finally:
        if database is not None:
            documents = list(database[DOCUMENTS_COLLECTION].find({"file_name": marker}, {"_id": 1}))
            document_ids = [item["_id"] for item in documents]
            versions = list(
                database[DOCUMENT_VERSIONS_COLLECTION].find(
                    {"document_id": {"$in": document_ids}}, {"_id": 1, "storage_key": 1}
                )
            ) if document_ids else []
            version_ids = [item["_id"] for item in versions]
            for version in versions:
                try:
                    if vector_index is not None:
                        vector_index.delete_version(version["_id"])
                    if storage is not None and version.get("storage_key"):
                        storage.delete(version["storage_key"])
                except (VectorIndexError, StorageError):
                    cleanup_ok = False
            if version_ids:
                database[INGESTION_JOBS_COLLECTION].delete_many(
                    {"version_id": {"$in": version_ids}}
                )
                database[DOCUMENT_VERSIONS_COLLECTION].delete_many(
                    {"_id": {"$in": version_ids}}
                )
            if document_ids:
                database[DOCUMENTS_COLLECTION].delete_many({"_id": {"$in": document_ids}})
            remaining = database[DOCUMENTS_COLLECTION].count_documents({"file_name": marker})
            cleanup_ok = cleanup_ok and remaining == 0
            print("Cleanup: PASS" if cleanup_ok else "Cleanup: FAILED")
        connections.close()


if __name__ == "__main__":
    raise SystemExit(main())
