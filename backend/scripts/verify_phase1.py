"""Live P1-07 verification trên namespace test riêng, có cleanup chính xác."""

import hashlib
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.document_indexes import (
    DOCUMENTS_COLLECTION,
    DOCUMENT_VERSIONS_COLLECTION,
    INGESTION_JOBS_COLLECTION,
)
from app.document_models import DocumentStatus
from app.document_repository import MongoDocumentRepository
from app.document_service import DocumentService
from app.ingestion import IngestionError, IngestionService
from app.main import app
from app.qdrant_ingestion import QdrantIngestionIndex, VectorIndexError
from app.rag.embeddings import get_embeddings
from app.storage import StorageError, create_file_storage

_TEST_NAME_PATTERN = r"^p1-07-verify-[0-9a-f-]{36}\.md$"


class FailingEmbeddings(Embeddings):
    def embed_documents(self, texts):
        raise TimeoutError("simulated verification failure")

    def embed_query(self, text):
        raise TimeoutError("simulated verification failure")


def _filter(document_id: str, version_id: str | None = None) -> Filter:
    conditions = [
        FieldCondition(key="document_id", match=MatchValue(value=document_id))
    ]
    if version_id is not None:
        conditions.append(
            FieldCondition(key="version_id", match=MatchValue(value=version_id))
        )
    return Filter(must=conditions)


def _cleanup(database, vector_index, storage, query: dict) -> bool:
    ok = True
    documents = list(database[DOCUMENTS_COLLECTION].find(query, {"_id": 1}))
    for document in documents:
        document_id = document["_id"]
        versions = list(
            database[DOCUMENT_VERSIONS_COLLECTION].find(
                {"document_id": document_id}, {"_id": 1, "storage_key": 1}
            )
        )
        version_ids = [version["_id"] for version in versions]
        try:
            vector_index.delete_document(document_id)
        except VectorIndexError:
            ok = False
        for version in versions:
            try:
                if version.get("storage_key"):
                    storage.delete(version["storage_key"])
            except StorageError:
                ok = False
        if version_ids:
            database[INGESTION_JOBS_COLLECTION].delete_many(
                {"version_id": {"$in": version_ids}}
            )
            database[DOCUMENT_VERSIONS_COLLECTION].delete_many(
                {"_id": {"$in": version_ids}}
            )
        database[DOCUMENTS_COLLECTION].delete_one({"_id": document_id})
    return ok and database[DOCUMENTS_COLLECTION].count_documents(query) == 0


def main() -> int:
    marker = f"p1-07-verify-{uuid4()}.md"
    first_content = b"# Verification\n\nThe active codename is ORCHID ALPHA."
    second_content = b"# Verification\n\nThe active codename is COBALT BETA."
    client = TestClient(app)
    entered = False
    database = None
    vector_index = None
    storage = None
    document_id = None
    stage = "startup"
    http_status = None
    cleanup_ok = True
    try:
        client.__enter__()
        entered = True
        cloud = app.state.cloud_connections
        database = cloud.mongodb.database
        if database is None or cloud.qdrant.client is None:
            print("BLOCKED: cloud dependencies chưa sẵn sàng; credentials không được in.")
            return 2
        vector_index = QdrantIngestionIndex(
            cloud.qdrant.client, settings.qdrant_collection
        )
        storage = create_file_storage(settings)
        if not _cleanup(
            database,
            vector_index,
            storage,
            {"file_name": {"$regex": _TEST_NAME_PATTERN}},
        ):
            raise RuntimeError("stale cleanup failed")

        stage = "upload"
        upload = client.post(
            "/documents/upload",
            files={"file": (marker, first_content, "text/markdown")},
        )
        http_status = upload.status_code
        if upload.status_code != 201:
            raise RuntimeError("upload failed")
        upload_data = upload.json()
        document_id = upload_data["document_id"]
        first_version_id = upload_data["version_id"]

        stage = "raw_metadata_chunks"
        first_version = database[DOCUMENT_VERSIONS_COLLECTION].find_one(
            {"_id": first_version_id}
        )
        if first_version is None or first_version.get("storage_key") is None:
            raise RuntimeError("version metadata missing")
        raw_checks = (
            storage.exists(first_version["storage_key"])
            and storage.read(first_version["storage_key"]) == first_content
            and first_version.get("checksum_sha256")
            == hashlib.sha256(first_content).hexdigest()
            and first_version.get("chunk_count") == upload_data["num_chunks"]
            and vector_index.count_version(first_version_id) == upload_data["num_chunks"]
        )
        if not raw_checks:
            raise RuntimeError("raw/metadata/chunk mismatch")

        stage = "qdrant_retrieval_v1"
        embeddings = get_embeddings()
        query_vector = embeddings.embed_query("What is the active codename?")
        first_hits = cloud.qdrant.client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            query_filter=_filter(document_id, first_version_id),
            limit=settings.top_k,
            with_payload=True,
        ).points
        required_payload = {
            "document_id",
            "version_id",
            "chunk_id",
            "chunk_index",
            "file_name",
            "page",
            "chunk_text",
        }
        if (
            not first_hits
            or not required_payload.issubset(first_hits[0].payload)
            or first_hits[0].payload["version_id"] != first_version_id
            or first_hits[0].payload["page"] is not None
        ):
            raise RuntimeError("retrieval/payload mismatch")

        stage = "version_switch"
        update = client.put(
            f"/documents/{document_id}",
            files={"file": (marker, second_content, "text/markdown")},
        )
        http_status = update.status_code
        if update.status_code != 201 or not update.json().get("activated"):
            raise RuntimeError("version update failed")
        second_version_id = update.json()["version_id"]
        document = database[DOCUMENTS_COLLECTION].find_one({"_id": document_id})
        if document is None or document.get("active_version_id") != second_version_id:
            raise RuntimeError("active version did not switch")
        second_hits = cloud.qdrant.client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            query_filter=_filter(document_id, second_version_id),
            limit=settings.top_k,
            with_payload=True,
        ).points
        if not second_hits or second_hits[0].payload["version_id"] != second_version_id:
            raise RuntimeError("active version retrieval failed")

        stage = "failed_reindex"
        repository = MongoDocumentRepository(database)
        failing_ingestion = IngestionService(
            repository=repository,
            storage=storage,
            vector_index=vector_index,
            embeddings=FailingEmbeddings(),
            embedding_model=settings.embedding_model,
        )
        failing_service = DocumentService(
            repository=repository,
            storage=storage,
            vector_index=vector_index,
            ingestion=failing_ingestion,
        )
        try:
            failing_service.reindex(document_id)
            raise RuntimeError("failed re-index unexpectedly succeeded")
        except IngestionError as exc:
            if exc.code != "embedding_failed":
                raise RuntimeError("unexpected re-index failure code") from exc
        document = database[DOCUMENTS_COLLECTION].find_one({"_id": document_id})
        failed_version = database[DOCUMENT_VERSIONS_COLLECTION].find_one(
            {"document_id": document_id, "status": DocumentStatus.FAILED.value},
            sort=[("version", -1)],
        )
        if (
            document is None
            or document.get("active_version_id") != second_version_id
            or failed_version is None
            or vector_index.count_version(failed_version["_id"]) != 0
        ):
            raise RuntimeError("failed re-index changed active version")

        stage = "delete_no_retrieval"
        deleted = client.delete(f"/documents/{document_id}")
        http_status = deleted.status_code
        if deleted.status_code != 200 or deleted.json().get("cleanup_pending"):
            raise RuntimeError("delete failed")
        after_delete = cloud.qdrant.client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            query_filter=_filter(document_id),
            limit=settings.top_k,
            with_payload=True,
        ).points
        document = database[DOCUMENTS_COLLECTION].find_one({"_id": document_id})
        if (
            after_delete
            or document is None
            or document.get("status") != DocumentStatus.DELETED.value
            or document.get("active_version_id") is not None
        ):
            raise RuntimeError("deleted document remains retrievable")

        print(
            "PASS: raw/checksum, metadata/page, chunk count, Qdrant retrieval, "
            "version switch, failed re-index và delete-no-retrieval đã xác minh."
        )
        return 0
    except Exception as exc:
        print(
            f"FAILED: stage={stage}; http_status={http_status}; "
            f"type={type(exc).__name__}; secrets/raw exception không được in."
        )
        return 1
    finally:
        if database is not None and vector_index is not None and storage is not None:
            query = {"_id": document_id} if document_id else {
                "file_name": {"$regex": _TEST_NAME_PATTERN}
            }
            cleanup_ok = _cleanup(database, vector_index, storage, query)
            print("Cleanup: PASS" if cleanup_ok else "Cleanup: FAILED")
        if entered:
            client.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main())
