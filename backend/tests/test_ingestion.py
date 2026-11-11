"""Integration-style unit tests P1-05 bằng Mongo fake, temp storage và Qdrant in-memory."""

import tempfile
import unittest
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from qdrant_client import QdrantClient

from app.documents.models import (
    DocumentStatus,
    IngestionJobRecord,
    IngestionJobStatus,
    utc_now,
)
from app.documents.repository import RepositoryConflictError, RepositoryError
from app.documents.service import DocumentService
from app.documents.migrations.demo_corpus import DemoCorpusMigration, MigrationSource
from app.documents.ingestion import IngestionError, IngestionService
from app.infrastructure.qdrant_vector_index import (
    QdrantVectorIndex,
    VectorCollectionMismatchError,
    VectorIndexError,
)
from app.infrastructure.storage import LocalFileStorage
from app.rag.vector_index import VectorFilter


class DeterministicEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[float(len(text)), 1.0, 0.5] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0, 0.5]


class FailingEmbeddings(DeterministicEmbeddings):
    def embed_documents(self, texts):
        raise TimeoutError("secret provider detail")


class MemoryRepository:
    def __init__(self):
        self.documents = {}
        self.versions = {}
        self.jobs = {}
        self.fail_finalize_once = False

    def create_upload(self, document, version, job):
        self.documents[document.document_id] = document
        self.versions[version.version_id] = version
        self.jobs[job.job_id] = job

    def get_document(self, document_id):
        return self.documents[document_id]

    def find_document_by_source_key(self, source_key):
        return next(
            (
                document
                for document in self.documents.values()
                if document.source_key == source_key
            ),
            None,
        )

    def get_version(self, version_id):
        return self.versions[version_id]

    def list_documents(self, *, include_deleted=False, offset=0, limit=100):
        values = sorted(
            self.documents.values(), key=lambda item: item.created_at, reverse=True
        )
        if not include_deleted:
            values = [item for item in values if item.status != DocumentStatus.DELETED]
        return values[offset:offset + limit]

    def list_versions(self, document_id):
        return sorted(
            (
                version for version in self.versions.values()
                if version.document_id == document_id
            ),
            key=lambda item: item.version,
            reverse=True,
        )

    def next_version_number(self, document_id):
        numbers = [
            version.version
            for version in self.versions.values()
            if version.document_id == document_id
        ]
        return max(numbers, default=0) + 1

    def create_version_upload(self, version, job):
        self.versions[version.version_id] = version
        self.jobs[job.job_id] = job

    def create_retry_job(self, version):
        attempts = [
            job.attempt for job in self.jobs.values() if job.version_id == version.version_id
        ]
        job = IngestionJobRecord(
            document_id=version.document_id,
            version_id=version.version_id,
            attempt=max(attempts, default=0) + 1,
        )
        self.jobs[job.job_id] = job
        return job

    def mark_processing(self, document_id, version_id, job_id):
        now = utc_now()
        if self.documents[document_id].status == DocumentStatus.DELETED:
            raise RepositoryConflictError("document deleted")
        self.versions[version_id] = self.versions[version_id].model_copy(
            update={"status": DocumentStatus.PROCESSING, "updated_at": now}
        )
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={
                "status": IngestionJobStatus.PROCESSING,
                "started_at": now,
                "updated_at": now,
            }
        )
        document = self.documents[document_id]
        if document.active_version_id is None:
            self.documents[document_id] = document.model_copy(
                update={"status": DocumentStatus.PROCESSING, "updated_at": now}
            )

    def set_chunk_plan(self, version_id, *, chunk_count, embedding_model, vector_collection):
        self.versions[version_id] = self.versions[version_id].model_copy(
            update={
                "chunk_count": chunk_count,
                "embedding_model": embedding_model,
                "vector_collection": vector_collection,
                "updated_at": utc_now(),
            }
        )

    def complete_and_activate(self, version_id, job_id):
        if self.fail_finalize_once:
            self.fail_finalize_once = False
            raise RepositoryError("simulated finalize failure")
        version = self.versions[version_id]
        document = self.documents[version.document_id]
        if document.status == DocumentStatus.DELETED:
            raise RepositoryConflictError("document deleted")
        active = self.versions.get(document.active_version_id)
        activated = active is None or active.version < version.version
        self.versions[version_id] = version.model_copy(
            update={
                "status": DocumentStatus.INDEXED,
                "indexed_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        if activated:
            self.documents[version.document_id] = document.model_copy(
                update={
                    "active_version_id": version_id,
                    "file_name": version.file_name,
                    "status": DocumentStatus.INDEXED,
                    "updated_at": utc_now(),
                }
            )
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={
                "status": IngestionJobStatus.COMPLETED,
                "completed_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        return activated

    def mark_failed(self, document_id, version_id, job_id, error_code):
        self.versions[version_id] = self.versions[version_id].model_copy(
            update={"status": DocumentStatus.FAILED, "updated_at": utc_now()}
        )
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={
                "status": IngestionJobStatus.FAILED,
                "error_code": error_code,
                "completed_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        document = self.documents[document_id]
        if document.active_version_id is None and document.status != DocumentStatus.DELETED:
            self.documents[document_id] = document.model_copy(
                update={"status": DocumentStatus.FAILED, "updated_at": utc_now()}
            )

    def is_active_version(self, document_id, version_id):
        return self.documents[document_id].active_version_id == version_id

    def is_document_deleted(self, document_id):
        return self.documents[document_id].status == DocumentStatus.DELETED

    def unpublish(self, document_id):
        document = self.documents[document_id]
        updated = document.model_copy(
            update={
                "status": DocumentStatus.DELETED,
                "active_version_id": None,
                "cleanup_pending": True,
                "deleted_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self.documents[document_id] = updated
        return updated

    def mark_cleanup_complete(self, document_id):
        self.documents[document_id] = self.documents[document_id].model_copy(
            update={"cleanup_pending": False, "updated_at": utc_now()}
        )

    def latest_processing_job(self, version_id):
        jobs = [
            job for job in self.jobs.values()
            if job.version_id == version_id and job.status == IngestionJobStatus.PROCESSING
        ]
        return max(jobs, key=lambda job: job.attempt)

    def list_processing_versions(self, limit=100):
        values = [
            version for version in self.versions.values()
            if version.status in {DocumentStatus.PROCESSING, DocumentStatus.INDEXED}
            and version.chunk_count > 0
            and any(
                job.version_id == version.version_id
                and job.status == IngestionJobStatus.PROCESSING
                for job in self.jobs.values()
            )
        ]
        return values[:limit]


class IngestionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp.name)
        self.storage = LocalFileStorage(self.temp_root / "storage")
        self.repository = MemoryRepository()
        self.qdrant = QdrantClient(":memory:")
        self.vector_index = QdrantVectorIndex(self.qdrant, "test_documents")

    def tearDown(self):
        self.qdrant.close()
        self.temp.cleanup()

    def service(self, embeddings=None):
        return IngestionService(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            embeddings=embeddings or DeterministicEmbeddings(),
            embedding_model="test-embedding",
        )

    def document_service(self):
        ingestion = self.service()
        return DocumentService(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            ingestion=ingestion,
        )

    def migration(self, *, ingestion=None):
        return DemoCorpusMigration(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            ingestion=ingestion or self.service(),
            embeddings=DeterministicEmbeddings(),
        )

    def test_successful_ingestion_saves_indexes_verifies_and_activates(self):
        result = self.service().ingest(file_name="guide.md", content=b"# Guide\n\nHello RAG")
        document = self.repository.documents[result.document_id]
        version = self.repository.versions[result.version_id]
        job = self.repository.jobs[result.job_id]

        self.assertTrue(result.activated)
        self.assertEqual(document.active_version_id, result.version_id)
        self.assertEqual(document.status, DocumentStatus.INDEXED)
        self.assertEqual(version.status, DocumentStatus.INDEXED)
        self.assertEqual(version.chunk_count, result.num_chunks)
        self.assertEqual(version.embedding_model, "test-embedding")
        self.assertTrue(self.storage.exists(version.storage_key))
        self.assertEqual(job.status, IngestionJobStatus.COMPLETED)
        self.assertEqual(
            self.vector_index.count(VectorFilter(version_id=result.version_id)),
            result.num_chunks,
        )
        points, _ = self.qdrant.scroll(
            collection_name="test_documents",
            scroll_filter=self.vector_index._to_qdrant_filter(
                VectorFilter(version_id=result.version_id)
            ),
            limit=10,
            with_payload=True,
            with_vectors=False,
        )
        self.assertEqual(points[0].payload["document_id"], result.document_id)
        self.assertEqual(points[0].payload["version_id"], result.version_id)
        self.assertEqual(points[0].payload["chunk_index"], 0)
        self.assertEqual(points[0].payload["file_name"], "guide.md")
        self.assertIn("chunk_text", points[0].payload)

    def test_failed_new_version_preserves_active_version_and_can_retry(self):
        first = self.service().ingest(file_name="guide.md", content=b"stable version")
        with self.assertRaises(IngestionError) as raised:
            self.service(FailingEmbeddings()).ingest(
                document_id=first.document_id,
                file_name="guide.md",
                content=b"candidate version",
            )
        self.assertEqual(raised.exception.code, "embedding_failed")

        document = self.repository.documents[first.document_id]
        failed = next(
            version for version in self.repository.versions.values()
            if version.document_id == first.document_id and version.version == 2
        )
        self.assertEqual(document.active_version_id, first.version_id)
        self.assertEqual(document.status, DocumentStatus.INDEXED)
        self.assertEqual(failed.status, DocumentStatus.FAILED)
        self.assertEqual(
            self.vector_index.count(VectorFilter(version_id=failed.version_id)), 0
        )

        retried = self.service().retry(failed.version_id)
        self.assertTrue(retried.activated)
        self.assertEqual(
            self.repository.documents[first.document_id].active_version_id,
            failed.version_id,
        )
        attempts = [
            job.attempt for job in self.repository.jobs.values()
            if job.version_id == failed.version_id
        ]
        self.assertEqual(sorted(attempts), [1, 2])

    def test_finalize_failure_is_reconciled_without_deleting_verified_vectors(self):
        self.repository.fail_finalize_once = True
        with self.assertRaises(IngestionError) as raised:
            self.service().ingest(file_name="recover.txt", content=b"recoverable content")
        self.assertEqual(raised.exception.code, "metadata_finalize_failed")
        version = next(iter(self.repository.versions.values()))
        self.assertGreater(
            self.vector_index.count(VectorFilter(version_id=version.version_id)), 0
        )

        summary = self.service().reconcile_processing()
        self.assertEqual(summary, {"completed": 1, "failed": 0, "skipped": 0})
        self.assertEqual(
            self.repository.documents[version.document_id].active_version_id,
            version.version_id,
        )

    def test_collection_schema_mismatch_is_rejected(self):
        self.vector_index.ensure_collection(3)
        with self.assertRaises(VectorCollectionMismatchError):
            self.vector_index.ensure_collection(4)

    def test_invalid_filename_is_rejected_before_storage_write(self):
        with self.assertRaises(IngestionError) as raised:
            self.service().ingest(file_name="../secret.md", content=b"data")
        self.assertEqual(raised.exception.code, "invalid_file_name")
        self.assertEqual(list(Path(self.temp.name).rglob("original")), [])

    def test_document_management_list_get_update_reindex_and_delete(self):
        service = self.document_service()
        first = service.ingestion.ingest(file_name="guide.md", content=b"version one")

        listed = service.list_documents()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].document.document_id, first.document_id)
        self.assertEqual(listed[0].version_count, 1)
        detail = service.get_document(first.document_id)
        self.assertEqual([version.version for version in detail.versions], [1])

        second = service.update(
            first.document_id, file_name="guide-v2.md", content=b"version two"
        )
        third = service.reindex(first.document_id)
        self.assertTrue(second.activated)
        self.assertTrue(third.activated)
        self.assertEqual(self.repository.versions[third.version_id].version, 3)
        self.assertEqual(self.storage.read(self.repository.versions[third.version_id].storage_key), b"version two")

        result = service.delete(first.document_id)
        document = self.repository.documents[first.document_id]
        self.assertEqual(document.status, DocumentStatus.DELETED)
        self.assertIsNone(document.active_version_id)
        self.assertFalse(result.cleanup_pending)
        self.assertEqual(result.retained_files, 3)
        self.assertEqual(
            self.vector_index.count(VectorFilter(document_id=first.document_id)), 0
        )
        self.assertTrue(
            all(
                self.storage.exists(version.storage_key)
                for version in self.repository.versions.values()
            )
        )
        self.assertEqual(service.list_documents(), [])
        self.assertEqual(len(service.list_documents(include_deleted=True)), 1)

        # DELETE lặp lại retry cleanup nhưng không xóa raw files hay history.
        repeated = service.delete(first.document_id)
        self.assertFalse(repeated.cleanup_pending)
        self.assertEqual(repeated.deleted_chunks, 0)
        self.assertEqual(repeated.retained_files, 3)

    def test_deleted_document_cannot_be_updated_or_reindexed(self):
        service = self.document_service()
        first = service.ingestion.ingest(file_name="guide.md", content=b"version one")
        service.delete(first.document_id)

        with self.assertRaises(IngestionError) as update_error:
            service.update(first.document_id, file_name="new.md", content=b"new")
        self.assertEqual(update_error.exception.code, "document_deleted")
        with self.assertRaises(IngestionError) as reindex_error:
            service.reindex(first.document_id)
        self.assertEqual(reindex_error.exception.code, "document_deleted")

    def test_delete_unpublishes_even_when_qdrant_cleanup_is_pending(self):
        service = self.document_service()
        first = service.ingestion.ingest(file_name="guide.md", content=b"version one")

        class UnavailableVectorIndex:
            def count(self, filters):
                raise VectorIndexError("unavailable")

        unavailable = DocumentService(
            repository=self.repository,
            storage=self.storage,
            vector_index=UnavailableVectorIndex(),
            ingestion=service.ingestion,
        )
        result = unavailable.delete(first.document_id)
        document = self.repository.documents[first.document_id]
        self.assertTrue(result.cleanup_pending)
        self.assertEqual(document.status, DocumentStatus.DELETED)
        self.assertIsNone(document.active_version_id)
        self.assertTrue(document.cleanup_pending)

    def test_qdrant_retrieval_payload_page_version_switch_and_delete(self):
        def page_loader(_path):
            return [
                Document(
                    page_content="verification marker",
                    metadata={"page": 7, "source": "fixture.pdf"},
                )
            ]

        ingestion = IngestionService(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            embeddings=DeterministicEmbeddings(),
            loader=page_loader,
            splitter=lambda documents: documents,
            embedding_model="test-embedding",
        )
        service = DocumentService(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            ingestion=ingestion,
        )
        first = ingestion.ingest(file_name="guide.pdf", content=b"first")
        second = service.update(
            first.document_id, file_name="guide.pdf", content=b"second"
        )
        active = self.repository.documents[first.document_id].active_version_id
        self.assertEqual(active, second.version_id)

        results = self.vector_index.query(
            DeterministicEmbeddings().embed_query("verification marker"),
            limit=5,
            filters=VectorFilter(
                document_id=first.document_id,
                version_id=active,
            ),
        )
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.document_id, first.document_id)
        self.assertEqual(result.version_id, second.version_id)
        self.assertEqual(result.chunk_index, 0)
        self.assertEqual(result.page, 7)
        self.assertEqual(result.chunk_text, "verification marker")

        service.delete(first.document_id)
        after_delete = self.vector_index.query(
            DeterministicEmbeddings().embed_query("verification marker"),
            limit=5,
            filters=VectorFilter(document_id=first.document_id),
        )
        self.assertEqual(after_delete, [])

    def test_demo_migration_is_idempotent_and_tracks_source_identity(self):
        source = self.temp_root / "demo.md"
        source.write_bytes(b"# Demo\n\nStable migration content")
        item = MigrationSource("demo-corpus-v1:demo", source)

        first = self.migration().migrate([item])
        second = self.migration().migrate([item])

        self.assertEqual(first.created, 1)
        self.assertEqual(first.failed, 0)
        self.assertEqual(second.verified, 1)
        self.assertEqual(second.failed, 0)
        self.assertEqual(len(self.repository.documents), 1)
        self.assertEqual(len(self.repository.versions), 1)
        document = next(iter(self.repository.documents.values()))
        self.assertEqual(document.source_key, item.source_key)

    def test_demo_migration_changed_source_creates_and_activates_new_version(self):
        source = self.temp_root / "demo.md"
        item = MigrationSource("demo-corpus-v1:demo", source)
        source.write_bytes(b"version one")
        first = self.migration().migrate([item]).items[0]
        source.write_bytes(b"version two with changed bytes")

        second = self.migration().migrate([item]).items[0]

        self.assertEqual(second.outcome, "UPDATED")
        self.assertEqual(first.document_id, second.document_id)
        self.assertNotEqual(first.version_id, second.version_id)
        self.assertEqual(len(self.repository.versions), 2)
        self.assertEqual(
            self.repository.documents[first.document_id].active_version_id,
            second.version_id,
        )

    def test_demo_migration_failure_does_not_replace_active_version(self):
        source = self.temp_root / "demo.md"
        item = MigrationSource("demo-corpus-v1:demo", source)
        source.write_bytes(b"working version")
        first = self.migration().migrate([item]).items[0]
        source.write_bytes(b"candidate that fails")
        failing_ingestion = self.service(FailingEmbeddings())

        failed = self.migration(ingestion=failing_ingestion).migrate([item]).items[0]

        self.assertEqual(failed.outcome, "FAILED")
        self.assertEqual(failed.error_code, "embedding_failed")
        self.assertEqual(
            self.repository.documents[first.document_id].active_version_id,
            first.version_id,
        )
        self.assertEqual(
            self.repository.versions[first.version_id].status,
            DocumentStatus.INDEXED,
        )

    def test_demo_migration_same_checksum_fails_verify_without_new_version(self):
        source = self.temp_root / "demo.md"
        source.write_bytes(b"content whose vectors disappear")
        item = MigrationSource("demo-corpus-v1:demo", source)
        first = self.migration().migrate([item]).items[0]
        self.vector_index.delete(VectorFilter(version_id=first.version_id))

        result = self.migration().migrate([item]).items[0]

        self.assertEqual(result.outcome, "FAILED")
        self.assertEqual(result.error_code, "vector_count_mismatch")
        self.assertEqual(len(self.repository.versions), 1)


if __name__ == "__main__":
    unittest.main()
