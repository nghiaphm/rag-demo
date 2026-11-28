"""Unit tests for Phase 5 safe Demo seed script (T5.2)."""

from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.seed_demo_workspace import (
    DEFAULT_DEMO_COLLECTION,
    DEMO_FIXTURE_SPECS,
    main as seed_main,
    run_dry_run_plan,
    validate_demo_target,
)
from app.documents.models import (
    DocumentRecord,
    DocumentStatus,
    DocumentVersionRecord,
    IngestionJobRecord,
)
from app.documents.migrations.demo_corpus import DemoCorpusMigration, MigrationSource


class _FakeDemoRepo:
    def __init__(self) -> None:
        self.docs: dict[str, DocumentRecord] = {}
        self.versions: dict[str, DocumentVersionRecord] = {}
        self.jobs: dict[str, IngestionJobRecord] = {}

    def find_document_by_source_key(self, source_key: str) -> DocumentRecord | None:
        return next((d for d in self.docs.values() if d.source_key == source_key), None)

    def create_document(self, doc: DocumentRecord) -> None:
        self.docs[doc.document_id] = doc

    def get_document(self, document_id: str) -> DocumentRecord:
        return self.docs[document_id]

    def get_version(self, version_id: str) -> DocumentVersionRecord:
        return self.versions[version_id]

    def next_version_number(self, document_id: str) -> int:
        return sum(1 for v in self.versions.values() if v.document_id == document_id) + 1

    def create_version(self, version: DocumentVersionRecord) -> None:
        self.versions[version.version_id] = version

    def create_job(self, job: IngestionJobRecord) -> None:
        self.jobs[job.job_id] = job

    def update_job_status(self, job_id: str, status, **kwargs) -> None:
        pass

    def mark_version_indexed(self, version_id: str, **kwargs) -> None:
        v = self.versions[version_id]
        v.status = DocumentStatus.INDEXED
        v.chunk_count = kwargs.get("chunk_count", 1)
        v.indexed_at = datetime.now(timezone.utc)

    def activate_version(self, document_id: str, version_id: str) -> None:
        d = self.docs[document_id]
        d.active_version_id = version_id
        d.status = DocumentStatus.INDEXED

    def update_document_status(self, document_id: str, status: DocumentStatus) -> None:
        self.docs[document_id].status = status


class _FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def write(self, key: str, content: bytes) -> None:
        self.files[key] = content

    def read(self, key: str) -> bytes:
        return self.files[key]


class _FakeVectorIndex:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, str]] = []

    def count(self, filters) -> int:
        return sum(
            1
            for doc_id, ver_id, _ in self.records
            if doc_id == filters.document_id and ver_id == filters.version_id
        )

    def query(self, _vec, *, limit: int = 1, filters=None):
        from types import SimpleNamespace

        return [
            SimpleNamespace(
                document_id=filters.document_id,
                version_id=filters.version_id,
                chunk_text="synthetic verified chunk",
            )
        ]


class _FakeEmbeddings:
    def embed_query(self, _text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _FakeIngestionService:
    def __init__(self, repo: _FakeDemoRepo, storage: _FakeStorage, vectors: _FakeVectorIndex) -> None:
        self.repo = repo
        self.storage = storage
        self.vectors = vectors

    def ingest(self, *, file_name: str, content: bytes, source_key: str | None = None, document_id: str | None = None):
        from types import SimpleNamespace

        if document_id is None:
            doc = DocumentRecord(file_name=file_name, source_key=source_key, status=DocumentStatus.UPLOADED)
            self.repo.create_document(doc)
        else:
            doc = self.repo.get_document(document_id)
        checksum = hashlib.sha256(content).hexdigest()
        ver_num = self.repo.next_version_number(doc.document_id)
        key = f"demo/{doc.document_id}/v{ver_num}/{file_name}"
        self.storage.write(key, content)
        version = DocumentVersionRecord(
            document_id=doc.document_id,
            version=ver_num,
            file_name=file_name,
            checksum_sha256=checksum,
            size_bytes=len(content),
            storage_key=key,
            chunk_count=1,
            status=DocumentStatus.INDEXED,
            indexed_at=datetime.now(timezone.utc),
        )
        self.repo.create_version(version)
        self.repo.activate_version(doc.document_id, version.version_id)
        self.vectors.records.append((doc.document_id, version.version_id, file_name))
        return SimpleNamespace(document_id=doc.document_id, version_id=version.version_id, activated=True)


class TestSeedDemoWorkspace(unittest.TestCase):
    def test_default_dry_run_has_zero_cloud_calls_and_validates_all_synthetic_fixtures(self) -> None:
        with patch("scripts.seed_demo_workspace.CloudConnections") as mock_cloud:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = seed_main([])

        self.assertEqual(exit_code, 0)
        mock_cloud.assert_not_called()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["mode"], "dry_run")
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["target"]["qdrant_collection"], DEFAULT_DEMO_COLLECTION)
        self.assertEqual(payload["total_fixtures"], len(DEMO_FIXTURE_SPECS))
        self.assertTrue(all(len(item["checksum_sha256"]) == 64 for item in payload["items"]))

    def test_blocks_writes_to_primary_rag_documents_without_explicit_confirmation(self) -> None:
        for mode_argv in (
            ["--qdrant-collection", "rag_documents"],
            ["--apply", "--qdrant-collection", "rag_documents"],
            ["--qdrant-collection", "RAG_DOCUMENTS"],
            ["--documents-dir", "./data/documents"],
        ):
            with self.subTest(argv=mode_argv):
                stderr = io.StringIO()
                with patch("scripts.seed_demo_workspace.CloudConnections") as mock_cloud:
                    with redirect_stderr(stderr):
                        code = seed_main(mode_argv)
                self.assertEqual(code, 2)
                self.assertIn("BLOCKED", stderr.getvalue())
                mock_cloud.assert_not_called()

        # Explicit confirmation unblocks target validation
        col, _ = validate_demo_target("rag_documents", allow_primary_collection=True)
        self.assertEqual(col, "rag_documents")

    def test_demo_seed_migration_is_idempotent_across_reruns(self) -> None:
        plan = run_dry_run_plan()
        repo = _FakeDemoRepo()
        storage = _FakeStorage()
        vectors = _FakeVectorIndex()
        embeddings = _FakeEmbeddings()
        ingestion = _FakeIngestionService(repo, storage, vectors)
        migration = DemoCorpusMigration(
            repository=repo,
            storage=storage,
            vector_index=vectors,
            ingestion=ingestion,  # type: ignore[arg-type]
            embeddings=embeddings,  # type: ignore[arg-type]
        )

        repo_root = Path(__file__).resolve().parents[3]
        spec_by_key = {s.source_key: s for s in DEMO_FIXTURE_SPECS}
        sources = [
            MigrationSource(
                item["source_key"],
                (repo_root / spec_by_key[item["source_key"]].relative_path).resolve(),
            )
            for item in plan["items"]
        ]

        first = migration.migrate(sources)
        self.assertEqual(first.created, len(sources))
        self.assertEqual(first.failed, 0)

        second = migration.migrate(sources)
        self.assertEqual(second.created, 0)
        self.assertEqual(second.updated, 0)
        self.assertEqual(second.verified, len(sources))
        self.assertEqual(second.failed, 0)
        self.assertEqual(len(repo.docs), len(sources))


if __name__ == "__main__":
    unittest.main()
