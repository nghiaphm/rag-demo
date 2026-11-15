"""Offline unit tests for Phase 5.1 Async Ingestion Worker (Redis/ARQ queue + 202 API)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient

from app.api.routes.documents import router as documents_router
from app.documents.ingestion import IngestionService
from app.documents.models import (
    DocumentStatus,
    IngestionJobRecord,
    IngestionJobStatus,
    utc_now,
)
from app.documents.ports import IngestionQueue, IngestionQueueError
from app.documents.repository import RepositoryNotFoundError
from app.documents.service import DocumentService
from app.infrastructure.ingestion_queue import ArqIngestionQueue, NoOpIngestionQueue, get_ingestion_queue
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.infrastructure.storage import LocalFileStorage
from app.rag.vector_index import VectorFilter
from app.workers.ingestion_worker import process_ingestion_job


class _DeterministicEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 0.5] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.5]


class _InMemoryDocumentRepository:
    def __init__(self) -> None:
        self.documents: dict = {}
        self.versions: dict = {}
        self.jobs: dict = {}

    def create_upload(self, document, version, job) -> None:
        self.documents[document.document_id] = document
        self.versions[version.version_id] = version
        self.jobs[job.job_id] = job

    def create_version_upload(self, version, job) -> None:
        if version.document_id not in self.documents:
            raise RepositoryNotFoundError("Document không tồn tại")
        self.versions[version.version_id] = version
        self.jobs[job.job_id] = job

    def get_document(self, document_id: str):
        if document_id not in self.documents:
            raise RepositoryNotFoundError("Document không tồn tại")
        return self.documents[document_id]

    def get_version(self, version_id: str):
        if version_id not in self.versions:
            raise RepositoryNotFoundError("Version không tồn tại")
        return self.versions[version_id]

    def get_job(self, job_id: str) -> IngestionJobRecord:
        if job_id not in self.jobs:
            raise RepositoryNotFoundError("Job không tồn tại")
        return self.jobs[job_id]

    def next_version_number(self, document_id: str) -> int:
        versions = [v.version for v in self.versions.values() if v.document_id == document_id]
        return 1 if not versions else max(versions) + 1

    def list_documents(self, *, include_deleted: bool = False, offset: int = 0, limit: int = 100):
        items = list(self.documents.values())
        if not include_deleted:
            items = [d for d in items if d.status != DocumentStatus.DELETED]
        return items[offset : offset + limit]

    def list_versions(self, document_id: str):
        return sorted(
            [v for v in self.versions.values() if v.document_id == document_id],
            key=lambda item: item.version,
            reverse=True,
        )

    def mark_processing(self, document_id: str, version_id: str, job_id: str) -> None:
        now = utc_now()
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={"status": IngestionJobStatus.PROCESSING, "started_at": now, "updated_at": now}
        )
        self.versions[version_id] = self.versions[version_id].model_copy(
            update={"status": DocumentStatus.PROCESSING, "updated_at": now}
        )
        doc = self.documents[document_id]
        if doc.active_version_id is None and doc.status != DocumentStatus.DELETED:
            self.documents[document_id] = doc.model_copy(
                update={"status": DocumentStatus.PROCESSING, "updated_at": now}
            )

    def set_chunk_plan(self, version_id: str, *, chunk_count: int, embedding_model: str, vector_collection: str) -> None:
        self.versions[version_id] = self.versions[version_id].model_copy(
            update={
                "chunk_count": chunk_count,
                "embedding_model": embedding_model,
                "vector_collection": vector_collection,
            }
        )

    def complete_and_activate(self, version_id: str, job_id: str) -> bool:
        now = utc_now()
        version = self.versions[version_id].model_copy(
            update={"status": DocumentStatus.INDEXED, "indexed_at": now, "updated_at": now}
        )
        self.versions[version_id] = version
        doc = self.documents[version.document_id]
        self.documents[version.document_id] = doc.model_copy(
            update={"status": DocumentStatus.INDEXED, "active_version_id": version_id, "updated_at": now}
        )
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={"status": IngestionJobStatus.COMPLETED, "completed_at": now, "updated_at": now}
        )
        return True

    def mark_failed(self, document_id: str, version_id: str, job_id: str, error_code: str) -> None:
        now = utc_now()
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={"status": IngestionJobStatus.FAILED, "error_code": error_code, "updated_at": now}
        )
        self.versions[version_id] = self.versions[version_id].model_copy(
            update={"status": DocumentStatus.FAILED, "updated_at": now}
        )
        doc = self.documents[document_id]
        if doc.active_version_id is None:
            self.documents[document_id] = doc.model_copy(
                update={"status": DocumentStatus.FAILED, "updated_at": now}
            )

    def is_document_deleted(self, document_id: str) -> bool:
        return self.documents[document_id].status == DocumentStatus.DELETED


class _SpyIngestionQueue(IngestionQueue):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.enqueued: list[tuple[str, str]] = []

    async def enqueue_ingestion(self, *, version_id: str, job_id: str) -> str | None:
        if self.fail:
            raise IngestionQueueError("Redis down")
        self.enqueued.append((version_id, job_id))
        return job_id


class _SpySemanticCache:
    def __init__(self) -> None:
        self.invalidations = 0

    async def invalidate_all(self) -> None:
        self.invalidations += 1


class TestAsyncIngestionWorker(unittest.TestCase):
    def _build_services(self, tmp_dir: str):
        repo = _InMemoryDocumentRepository()
        storage = LocalFileStorage(Path(tmp_dir))
        qdrant = QdrantVectorIndex(QdrantClient(":memory:"), "async_docs")
        embeddings = _DeterministicEmbeddings()
        ingestion = IngestionService(
            repository=repo,
            storage=storage,
            vector_index=qdrant,
            embeddings=embeddings,
            embedding_model="test-embed",
        )
        doc_service = DocumentService(
            repository=repo,
            storage=storage,
            vector_index=qdrant,
            ingestion=ingestion,
        )
        return repo, qdrant, ingestion, doc_service

    def test_prepare_ingest_and_worker_process_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo, qdrant, ingestion, _ = self._build_services(tmp_dir)
            prepared = ingestion.prepare_ingest(
                file_name="async-guide.md",
                content=b"# Async Ingestion\n\nARQ worker parses chunks asynchronously.",
            )
            self.assertEqual(prepared.status, DocumentStatus.UPLOADED)
            self.assertFalse(prepared.activated)
            self.assertEqual(prepared.num_chunks, 0)
            self.assertEqual(repo.get_document(prepared.document_id).status, DocumentStatus.UPLOADED)
            self.assertEqual(repo.get_job(prepared.job_id).status, IngestionJobStatus.PENDING)
            self.assertEqual(qdrant.count(VectorFilter(version_id=prepared.version_id)), 0)

            cache = _SpySemanticCache()
            worker_result = asyncio.run(
                process_ingestion_job(
                    {"ingestion_service": ingestion, "semantic_cache": cache},
                    prepared.version_id,
                    prepared.job_id,
                )
            )
            self.assertEqual(worker_result["status"], DocumentStatus.INDEXED.value)
            self.assertTrue(worker_result["activated"])
            self.assertGreaterEqual(worker_result["num_chunks"], 1)
            self.assertEqual(repo.get_document(prepared.document_id).status, DocumentStatus.INDEXED)
            self.assertEqual(repo.get_job(prepared.job_id).status, IngestionJobStatus.COMPLETED)
            self.assertGreaterEqual(qdrant.count(VectorFilter(version_id=prepared.version_id)), 1)
            self.assertEqual(cache.invalidations, 1)

    def test_arq_queue_adapter_and_factory(self) -> None:
        self.assertIsInstance(get_ingestion_queue(SimpleNamespace(async_ingestion_enabled=False)), NoOpIngestionQueue)
        adapter = get_ingestion_queue(SimpleNamespace(async_ingestion_enabled=True, redis_url="redis://localhost:6379/0"))
        self.assertIsInstance(adapter, ArqIngestionQueue)

        calls: list[tuple] = []
        closed = False

        class _FakePool:
            async def enqueue_job(self, func_name, *args, _job_id=None):
                calls.append((func_name, args, _job_id))
                return SimpleNamespace(job_id=_job_id)

            async def aclose(self):
                nonlocal closed
                closed = True

        async def _factory(dsn):
            self.assertEqual(dsn, "redis://localhost:6379/0")
            return _FakePool()

        queue = ArqIngestionQueue(redis_url="redis://localhost:6379/0", pool_factory=_factory)
        returned_id = asyncio.run(queue.enqueue_ingestion(version_id="v-1", job_id="j-1"))
        self.assertEqual(returned_id, "j-1")
        self.assertEqual(calls, [("process_ingestion_job", ("v-1", "j-1"), "j-1")])
        asyncio.run(queue.close())
        self.assertTrue(closed)

    def test_upload_and_update_return_202_when_async_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo, _, _, doc_service = self._build_services(tmp_dir)
            queue = _SpyIngestionQueue()

            app = FastAPI()
            app.include_router(documents_router)
            app.state.cloud_connections = SimpleNamespace(
                mongodb=SimpleNamespace(database=object()),
                qdrant=SimpleNamespace(client=object()),
            )
            app.state.ingestion_queue = queue
            client = TestClient(app)

            with (
                patch("app.api.routes.documents.create_document_service", return_value=doc_service),
                patch("app.api.routes.documents.settings", SimpleNamespace(async_ingestion_enabled=True, auth_enabled=False)),
                patch("app.api.dependencies.auth.settings", SimpleNamespace(auth_enabled=False)),
            ):
                up_resp = client.post(
                    "/documents/upload",
                    files={"file": ("notes.txt", b"hello async world", "text/plain")},
                )
                self.assertEqual(up_resp.status_code, 202)
                up_body = up_resp.json()
                self.assertEqual(up_body["status"], "UPLOADED")
                self.assertFalse(up_body["activated"])
                self.assertEqual(up_body["num_chunks"], 0)
                self.assertEqual(len(queue.enqueued), 1)
                self.assertEqual(queue.enqueued[0], (up_body["version_id"], up_body["job_id"]))

                upd_resp = client.put(
                    f"/documents/{up_body['document_id']}",
                    files={"file": ("notes-v2.txt", b"hello async v2", "text/plain")},
                )
                self.assertEqual(upd_resp.status_code, 202)
                upd_body = upd_resp.json()
                self.assertEqual(upd_body["status"], "UPLOADED")
                self.assertEqual(len(queue.enqueued), 2)
                self.assertEqual(queue.enqueued[1], (upd_body["version_id"], upd_body["job_id"]))

            # Enqueue failure marks version/job FAILED and returns 503.
            app.state.ingestion_queue = _SpyIngestionQueue(fail=True)
            with (
                patch("app.api.routes.documents.create_document_service", return_value=doc_service),
                patch("app.api.routes.documents.settings", SimpleNamespace(async_ingestion_enabled=True, auth_enabled=False)),
                patch("app.api.dependencies.auth.settings", SimpleNamespace(auth_enabled=False)),
            ):
                fail_resp = client.post(
                    "/documents/upload",
                    files={"file": ("broken.txt", b"will fail enqueue", "text/plain")},
                )
                self.assertEqual(fail_resp.status_code, 503)
                failed_jobs = [j for j in repo.jobs.values() if j.status == IngestionJobStatus.FAILED]
                self.assertEqual(len(failed_jobs), 1)
                self.assertEqual(failed_jobs[0].error_code, "queue_unavailable")


if __name__ == "__main__":
    unittest.main()
