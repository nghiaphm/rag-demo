"""Live P1-06 API smoke với namespace riêng và cleanup chính xác."""

import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.shared.config import settings
from app.documents.indexes import (
    DOCUMENTS_COLLECTION,
    DOCUMENT_VERSIONS_COLLECTION,
    INGESTION_JOBS_COLLECTION,
)
from app.documents.models import DocumentStatus
from app.main import app
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex, VectorIndexError
from app.documents.ports import StorageError
from app.infrastructure.storage import create_file_storage
from app.rag.vector_index import VectorFilter


def main() -> int:
    marker = f"p1-06-smoke-{uuid4()}.md"
    document_id = None
    database = None
    vector_index = None
    storage = None
    cleanup_ok = True
    stage = "startup"
    http_status = None
    client = TestClient(app)
    try:
        client.__enter__()
        cloud = app.state.cloud_connections
        database = cloud.mongodb.database
        if database is None or cloud.qdrant.client is None:
            print("BLOCKED: cloud dependencies chưa sẵn sàng; credentials không được in.")
            return 2
        vector_index = QdrantVectorIndex(
            cloud.qdrant.client, settings.qdrant_collection
        )
        storage = create_file_storage(settings)

        # Chỉ dọn namespace smoke test P1-06 từ lần chạy bị gián đoạn trước đó.
        stale_documents = list(
            database[DOCUMENTS_COLLECTION].find(
                {"file_name": {"$regex": r"^p1-06-smoke-[0-9a-f-]{36}\.md$"}},
                {"_id": 1},
            )
        )
        for stale in stale_documents:
            stale_id = stale["_id"]
            stale_versions = list(
                database[DOCUMENT_VERSIONS_COLLECTION].find(
                    {"document_id": stale_id}, {"_id": 1, "storage_key": 1}
                )
            )
            stale_version_ids = [item["_id"] for item in stale_versions]
            vector_index.delete(VectorFilter(document_id=stale_id))
            for stale_version in stale_versions:
                if stale_version.get("storage_key"):
                    storage.delete(stale_version["storage_key"])
            if stale_version_ids:
                database[INGESTION_JOBS_COLLECTION].delete_many(
                    {"version_id": {"$in": stale_version_ids}}
                )
                database[DOCUMENT_VERSIONS_COLLECTION].delete_many(
                    {"_id": {"$in": stale_version_ids}}
                )
            database[DOCUMENTS_COLLECTION].delete_one({"_id": stale_id})
        if stale_documents:
            print("Stale test cleanup: PASS")

        stage = "upload"
        upload = client.post(
            "/documents/upload",
            files={"file": (marker, b"# P1-06\n\nversion one", "text/markdown")},
        )
        http_status = upload.status_code
        if upload.status_code != 201:
            raise RuntimeError("upload status mismatch")
        document_id = upload.json()["document_id"]

        stage = "list_get"
        listed = client.get("/documents")
        detail = client.get(f"/documents/{document_id}")
        http_status = detail.status_code
        if listed.status_code != 200 or detail.status_code != 200:
            raise RuntimeError("list/get status mismatch")
        if not any(item["document_id"] == document_id for item in listed.json()):
            raise RuntimeError("uploaded document missing from list")

        stage = "update"
        update = client.put(
            f"/documents/{document_id}",
            files={"file": (marker, b"# P1-06\n\nversion two", "text/markdown")},
        )
        http_status = update.status_code
        if update.status_code != 201 or not update.json().get("activated"):
            raise RuntimeError("update failed")

        stage = "reindex"
        reindex = client.post(f"/documents/{document_id}/re-index")
        http_status = reindex.status_code
        if reindex.status_code != 201 or not reindex.json().get("activated"):
            raise RuntimeError("re-index failed")

        stage = "delete"
        deleted = client.delete(f"/documents/{document_id}")
        http_status = deleted.status_code
        if deleted.status_code != 200:
            raise RuntimeError("delete status mismatch")
        deletion = deleted.json()
        if deletion.get("cleanup_pending") or deletion.get("raw_file_policy") != "retained":
            raise RuntimeError("delete policy mismatch")

        first_deleted_at = database[DOCUMENTS_COLLECTION].find_one(
            {"_id": document_id}, {"deleted_at": 1}
        ).get("deleted_at")
        stage = "delete_retry"
        repeated_delete = client.delete(f"/documents/{document_id}")
        http_status = repeated_delete.status_code
        if (
            repeated_delete.status_code != 200
            or repeated_delete.json().get("cleanup_pending")
            or repeated_delete.json().get("deleted_chunks") != 0
        ):
            raise RuntimeError("idempotent delete mismatch")

        stage = "verify"
        document = database[DOCUMENTS_COLLECTION].find_one({"_id": document_id})
        versions = list(
            database[DOCUMENT_VERSIONS_COLLECTION].find({"document_id": document_id})
        )
        checks = {
            "metadata_unpublished": document is not None
            and document.get("status") == DocumentStatus.DELETED.value
            and document.get("active_version_id") is None
            and document.get("cleanup_pending") is False,
            "deletion_timestamp_stable": document is not None
            and document.get("deleted_at") == first_deleted_at,
            "three_versions": len(versions) == 3,
            "qdrant_empty": vector_index.count(
                VectorFilter(document_id=document_id)
            ) == 0,
            "raw_retained": all(
                version.get("storage_key") and storage.exists(version["storage_key"])
                for version in versions
            ),
            "hidden_from_default_list": all(
                item["document_id"] != document_id
                for item in client.get("/documents").json()
            ),
        }
        if not all(checks.values()):
            raise RuntimeError("verification mismatch")
        print("PASS: upload/list/get/update/re-index/delete và retention policy đã xác minh.")
        return 0
    except Exception as exc:
        print(
            f"FAILED: stage={stage}; http_status={http_status}; type={type(exc).__name__}; "
            "secrets/raw exception không được in."
        )
        return 1
    finally:
        if database is not None and document_id is not None:
            versions = list(
                database[DOCUMENT_VERSIONS_COLLECTION].find(
                    {"document_id": document_id}, {"_id": 1, "storage_key": 1}
                )
            )
            version_ids = [item["_id"] for item in versions]
            try:
                if vector_index is not None:
                    vector_index.delete(VectorFilter(document_id=document_id))
            except VectorIndexError:
                cleanup_ok = False
            for version in versions:
                try:
                    if storage is not None and version.get("storage_key"):
                        storage.delete(version["storage_key"])
                except StorageError:
                    cleanup_ok = False
            if version_ids:
                database[INGESTION_JOBS_COLLECTION].delete_many(
                    {"version_id": {"$in": version_ids}}
                )
                database[DOCUMENT_VERSIONS_COLLECTION].delete_many(
                    {"_id": {"$in": version_ids}}
                )
            database[DOCUMENTS_COLLECTION].delete_one({"_id": document_id})
            cleanup_ok = cleanup_ok and (
                database[DOCUMENTS_COLLECTION].count_documents({"_id": document_id}) == 0
            )
            print("Cleanup: PASS" if cleanup_ok else "Cleanup: FAILED")
        client.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main())
