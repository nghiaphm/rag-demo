"""Live M-05 verification for Qdrant runtime cutover, with exact test cleanup."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.cloud_connections import CloudConnections
from app.config import settings
from app.document_indexes import (
    DOCUMENTS_COLLECTION,
    DOCUMENT_VERSIONS_COLLECTION,
    INGESTION_JOBS_COLLECTION,
)
from app.document_repository import MongoDocumentRepository
from app.document_service import DocumentService
from app.ingestion import IngestionService
from app.main import app
from app.qdrant_ingestion import QdrantVectorIndex
from app.rag.embeddings import get_embeddings
from app.rag.retriever import get_retriever
from app.storage import StorageError, create_file_storage
from app.vector_index import VectorFilter, VectorIndexError

BASELINE_COUNTS = {
    "enterprise_it_knowledge_base.xlsx": 37,
    "research_paper_1_ai_rag.pdf": 16,
    "research_paper_2_go_microservices.pdf": 15,
}
DEMO_SOURCE_PREFIX = "demo-corpus-v1:"
FALLBACK_PHRASE = "Không tìm thấy thông tin trong tài liệu"


def _cleanup(database, vector_index, storage, document_id: str | None) -> bool:
    if document_id is None:
        return True
    ok = True
    versions = list(
        database[DOCUMENT_VERSIONS_COLLECTION].find(
            {"document_id": document_id}, {"_id": 1, "storage_key": 1}
        )
    )
    try:
        vector_index.delete(VectorFilter(document_id=document_id))
    except VectorIndexError:
        ok = False
    for version in versions:
        if version.get("storage_key"):
            try:
                storage.delete(version["storage_key"])
            except StorageError:
                ok = False
    version_ids = [version["_id"] for version in versions]
    if version_ids:
        database[INGESTION_JOBS_COLLECTION].delete_many(
            {"version_id": {"$in": version_ids}}
        )
        database[DOCUMENT_VERSIONS_COLLECTION].delete_many(
            {"_id": {"$in": version_ids}}
        )
    database[DOCUMENTS_COLLECTION].delete_one({"_id": document_id})
    return ok and database[DOCUMENTS_COLLECTION].count_documents({"_id": document_id}) == 0


def main() -> int:
    connections = CloudConnections()
    database = None
    vector_index = None
    storage = None
    test_document_id = None
    cleanup_ok = True
    stage = "connect"
    try:
        statuses = connections.connect_all()
        if not all(status.ok for status in statuses.values()):
            print("BLOCKED: cloud dependencies chưa sẵn sàng; credentials không được in.")
            return 2
        database = connections.mongodb.database
        qdrant_client = connections.qdrant.client
        if database is None or qdrant_client is None:
            print("BLOCKED: cloud clients chưa sẵn sàng.")
            return 2

        repository = MongoDocumentRepository(database)
        vector_index = QdrantVectorIndex(qdrant_client, settings.qdrant_collection)
        storage = create_file_storage(settings)
        embeddings = get_embeddings()

        stage = "document_chunk_counts"
        demo_documents = list(database[DOCUMENTS_COLLECTION].find(
            {"source_key": {"$regex": f"^{DEMO_SOURCE_PREFIX}"}}
        ))
        if len(demo_documents) != len(BASELINE_COUNTS):
            raise RuntimeError("demo document count mismatch")
        total_chunks = 0
        pdf_document = None
        for document in demo_documents:
            active_id = document.get("active_version_id")
            version = database[DOCUMENT_VERSIONS_COLLECTION].find_one({"_id": active_id})
            expected = BASELINE_COUNTS.get(document.get("file_name"))
            if version is None or expected is None or version.get("chunk_count") != expected:
                raise RuntimeError("Mongo active-version count mismatch")
            actual = vector_index.count(VectorFilter(version_id=active_id))
            if actual != expected:
                raise RuntimeError("Qdrant chunk count mismatch")
            total_chunks += actual
            if document.get("file_name") == "research_paper_1_ai_rag.pdf":
                pdf_document = document
        if total_chunks != sum(BASELINE_COUNTS.values()):
            raise RuntimeError("total chunk count mismatch")

        stage = "retrieval_and_page_metadata"
        retriever = get_retriever(
            database=database,
            qdrant_client=qdrant_client,
            embeddings=embeddings,
        )
        queries = (
            ("Retrieval-Augmented Generation architecture", "research_paper_1_ai_rag.pdf"),
            ("Go microservices architecture", "research_paper_2_go_microservices.pdf"),
            ("enterprise IT knowledge base", "enterprise_it_knowledge_base.xlsx"),
        )
        for query, expected_file in queries:
            documents = retriever.invoke(query)
            if expected_file not in {item.metadata.get("file_name") for item in documents}:
                raise RuntimeError("demo retrieval source mismatch")
        if pdf_document is None:
            raise RuntimeError("PDF demo metadata missing")
        page_hits = vector_index.query(
            embeddings.embed_query("Retrieval-Augmented Generation"),
            limit=5,
            filters=VectorFilter(version_id=pdf_document["active_version_id"]),
        )
        if not page_hits or not all(hit.page is not None for hit in page_hits):
            raise RuntimeError("PDF page metadata missing")

        stage = "product_api_qa"
        with TestClient(app) as client:
            dependency_response = client.get("/health/dependencies")
            chat_response = client.post(
                "/chat",
                json={
                    "question": (
                        "Theo tài liệu, Retrieval-Augmented Generation kết hợp "
                        "những thành phần nào?"
                    )
                },
            )
        if dependency_response.status_code != 200 or chat_response.status_code != 200:
            raise RuntimeError("product API readiness/Q&A failed")
        qa = chat_response.json()
        if (
            not qa["answer"].strip()
            or FALLBACK_PHRASE in qa["answer"]
            or "research_paper_1_ai_rag.pdf"
            not in {source.get("file_name") for source in qa["sources"]}
        ):
            raise RuntimeError("product Q&A verification failed")

        stage = "active_version_and_delete"
        ingestion = IngestionService(
            repository=repository,
            storage=storage,
            vector_index=vector_index,
            embeddings=embeddings,
            embedding_model=settings.embedding_model,
        )
        service = DocumentService(
            repository=repository,
            storage=storage,
            vector_index=vector_index,
            ingestion=ingestion,
        )
        marker = uuid4().hex
        first = ingestion.ingest(
            file_name=f"m05-cutover-{marker}.md",
            content=f"Inactive marker OLD-{marker}.".encode(),
        )
        test_document_id = first.document_id
        second = service.update(
            first.document_id,
            file_name=f"m05-cutover-{marker}.md",
            content=f"Active marker NEW-{marker}.".encode(),
        )
        active_documents = retriever.invoke(f"OLD-{marker}")
        if any(item.metadata.get("version_id") == first.version_id for item in active_documents):
            raise RuntimeError("inactive version leaked into retrieval")
        if repository.get_document(first.document_id).active_version_id != second.version_id:
            raise RuntimeError("version activation mismatch")
        deleted = service.delete(first.document_id)
        if deleted.cleanup_pending or vector_index.count(
            VectorFilter(document_id=first.document_id)
        ) != 0:
            raise RuntimeError("delete cleanup mismatch")
        after_delete = retriever.invoke(f"NEW-{marker}")
        if any(item.metadata.get("document_id") == first.document_id for item in after_delete):
            raise RuntimeError("deleted document remains retrievable")

        print(
            "PASS: counts 3 documents/68 chunks, demo retrieval, product Q&A, "
            "PDF page metadata, active-version filter và delete-no-retrieval."
        )
        return 0
    except Exception:
        print(f"FAILED: stage={stage}; raw error/credentials không được in.")
        return 1
    finally:
        if database is not None and vector_index is not None and storage is not None:
            cleanup_ok = _cleanup(
                database, vector_index, storage, test_document_id
            )
        connections.close()
        print(f"Cleanup: {'PASS' if cleanup_ok else 'FAIL'}")


if __name__ == "__main__":
    raise SystemExit(main())
