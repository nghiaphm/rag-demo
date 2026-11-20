"""Integration tests cho Giai đoạn 1: S3 upload flow (sync/async), rollback và cross-backend routing."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from qdrant_client import QdrantClient

from app.documents.attachments import preview_version
from app.documents.ingestion import IngestionError, IngestionService
from app.documents.models import DocumentStatus
from app.documents.repository import RepositoryError
from app.documents.service import DocumentService
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.infrastructure.s3_storage import S3FileStorage
from app.infrastructure.storage import LocalFileStorage
from app.shared.auth import UserContext
from tests.integration.test_ingestion import DeterministicEmbeddings, MemoryRepository
from tests.unit.test_storage_backends import StubS3Client


def _build_sample_xlsx_bytes(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "NhanSu"
    ws.append(["MaNV", "HoTen", "PhongBan", "Luong"])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


class S3MemoryRepository(MemoryRepository):
    def get_job(self, job_id: str):
        return self.jobs[job_id]


class S3UploadFlowIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.local_root = Path(self.temp_dir.name)
        self.local_storage = LocalFileStorage(self.local_root)
        self.s3_stub = StubS3Client()
        self.s3_storage = S3FileStorage(bucket="rag-s3-test-bucket", client=self.s3_stub)
        self.repository = S3MemoryRepository()
        self.qdrant = QdrantClient(":memory:")
        self.vector_index = QdrantVectorIndex(self.qdrant, "test_s3_upload_flow")

    def tearDown(self) -> None:
        self.qdrant.close()
        self.temp_dir.cleanup()

    def _storage_resolver(self, backend_name: str):
        if backend_name == "s3":
            return self.s3_storage
        return self.local_storage

    def _make_service(self, *, primary_backend: str = "s3") -> DocumentService:
        primary = self.s3_storage if primary_backend == "s3" else self.local_storage
        ingestion = IngestionService(
            repository=self.repository,
            storage=primary,
            vector_index=self.vector_index,
            embeddings=DeterministicEmbeddings(),
            storage_resolver=self._storage_resolver,
        )
        return DocumentService(
            repository=self.repository,
            storage=primary,
            vector_index=self.vector_index,
            ingestion=ingestion,
            storage_resolver=self._storage_resolver,
        )

    def test_sync_excel_upload_stores_versioned_s3_key_and_records_backend(self) -> None:
        service = self._make_service(primary_backend="s3")
        user_ctx = UserContext(user_id="user-1", username="hr_admin", tenant_id="default")
        xlsx_bytes = _build_sample_xlsx_bytes([
            ["NV001", "Nguyễn Minh Anh", "Kỹ thuật", 25000000],
            ["NV002", "Trần Quốc Bảo", "Nhân sự", 18000000],
        ])

        result = service.ingestion.ingest(
            file_name="hr_employees.xlsx",
            content=xlsx_bytes,
            tenant_id=user_ctx.tenant_id,
            owner_id=user_ctx.user_id,
        )
        self.assertEqual(result.status, DocumentStatus.INDEXED)
        self.assertTrue(result.activated)
        self.assertGreater(result.num_chunks, 0)

        expected_v1_key = f"default/{result.document_id}/v1/original.xlsx"
        version_record = self.repository.get_version(result.version_id)
        doc_record = self.repository.get_document(result.document_id)

        self.assertEqual(doc_record.tenant_id, "default")
        self.assertEqual(version_record.storage_key, expected_v1_key)
        self.assertEqual(version_record.storage_backend, "s3")
        self.assertTrue(self.s3_storage.exists(expected_v1_key))
        self.assertEqual(self.s3_storage.get(expected_v1_key), xlsx_bytes)

        # Updating creates v2 without overwriting v1 on S3
        xlsx_v2 = _build_sample_xlsx_bytes([
            ["NV001", "Nguyễn Minh Anh", "Kỹ thuật", 28000000],
        ])
        v2_result = service.update(
            result.document_id,
            file_name="hr_employees.xlsx",
            content=xlsx_v2,
        )
        expected_v2_key = f"default/{result.document_id}/v2/original.xlsx"
        self.assertEqual(
            self.repository.get_version(v2_result.version_id).storage_key,
            expected_v2_key,
        )
        self.assertEqual(self.s3_storage.get(expected_v1_key), xlsx_bytes)
        self.assertEqual(self.s3_storage.get(expected_v2_key), xlsx_v2)

    def test_async_prepare_ingest_and_worker_process_version_on_s3(self) -> None:
        service = self._make_service(primary_backend="s3")
        xlsx_bytes = _build_sample_xlsx_bytes([
            ["NV010", "Lê Hoàng Nam", "Kinh doanh", 21000000],
        ])

        prepared = service.ingestion.prepare_ingest(
            file_name="sales_team.xlsx",
            content=xlsx_bytes,
            tenant_id="default",
        )
        self.assertEqual(prepared.status, DocumentStatus.UPLOADED)
        self.assertFalse(prepared.activated)
        expected_key = f"default/{prepared.document_id}/v1/original.xlsx"
        self.assertTrue(self.s3_storage.exists(expected_key))

        completed = service.ingestion.process_version(prepared.version_id, prepared.job_id)
        self.assertEqual(completed.status, DocumentStatus.INDEXED)
        self.assertTrue(completed.activated)
        self.assertGreater(completed.num_chunks, 0)

    def test_mongo_create_upload_failure_rolls_back_s3_object(self) -> None:
        service = self._make_service(primary_backend="s3")

        def fail_create_upload(document, version, job):
            raise RepositoryError("simulated mongo outage")

        self.repository.create_upload = fail_create_upload  # type: ignore[method-assign]
        xlsx_bytes = _build_sample_xlsx_bytes([["NV001", "Test", "HR", 1000]])

        with self.assertRaises(IngestionError) as ctx:
            service.ingestion.ingest(file_name="rollback.xlsx", content=xlsx_bytes)
        self.assertEqual(ctx.exception.code, "metadata_create_failed")
        self.assertEqual(self.s3_stub.objects, {})

    def test_preview_and_reindex_route_to_version_specific_storage_backend(self) -> None:
        # 1. Ingest v1 when primary backend is "local"
        local_service = self._make_service(primary_backend="local")
        v1_xlsx = _build_sample_xlsx_bytes([
            ["NV001", "Bản Local V1", "Kỹ thuật", 15000000],
        ])
        v1_res = local_service.ingestion.ingest(
            file_name="mixed_backends.xlsx",
            content=v1_xlsx,
        )
        v1_record = self.repository.get_version(v1_res.version_id)
        self.assertEqual(v1_record.storage_backend, "local")
        self.assertTrue(self.local_storage.exists(v1_record.storage_key))
        self.assertFalse(self.s3_storage.exists(v1_record.storage_key))

        # 2. Switch primary backend to "s3" and upload v2
        s3_service = self._make_service(primary_backend="s3")
        v2_xlsx = _build_sample_xlsx_bytes([
            ["NV002", "Bản S3 V2", "Nhân sự", 22000000],
        ])
        v2_res = s3_service.update(
            v1_res.document_id,
            file_name="mixed_backends.xlsx",
            content=v2_xlsx,
        )
        v2_record = self.repository.get_version(v2_res.version_id)
        self.assertEqual(v2_record.storage_backend, "s3")
        self.assertTrue(self.s3_storage.exists(v2_record.storage_key))

        # 3. Preview v1 (local) and v2 (s3) while running s3_service
        preview_v1 = preview_version(
            s3_service.repository,
            s3_service.storage,
            v1_res.document_id,
            v1_res.version_id,
            storage_resolver=s3_service.resolve_storage,
        )
        self.assertEqual(preview_v1["kind"], "excel")
        self.assertEqual(preview_v1["sheets"][0]["rows"][0][1], "Bản Local V1")

        preview_v2 = preview_version(
            s3_service.repository,
            s3_service.storage,
            v1_res.document_id,
            v2_res.version_id,
            storage_resolver=s3_service.resolve_storage,
        )
        self.assertEqual(preview_v2["kind"], "excel")
        self.assertEqual(preview_v2["sheets"][0]["rows"][0][1], "Bản S3 V2")

        # 4. Reindex when active version is v1 (local) while service primary is s3
        self.repository.documents[v1_res.document_id] = self.repository.documents[
            v1_res.document_id
        ].model_copy(update={"active_version_id": v1_res.version_id})
        v3_res = s3_service.reindex(v1_res.document_id)
        v3_record = self.repository.get_version(v3_res.version_id)
        self.assertEqual(v3_record.version, 3)
        self.assertEqual(v3_record.storage_backend, "s3")
        self.assertEqual(self.s3_storage.get(v3_record.storage_key), v1_xlsx)


if __name__ == "__main__":
    unittest.main()
