"""Integration tests cho Giai đoạn 2: xuất Parquet + Table Catalog vào MongoDB khi ingest .xlsx."""

from __future__ import annotations

import io
import unittest
from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook
import pyarrow.parquet as pq
from qdrant_client import QdrantClient

from app.documents.indexes import (
    DOCUMENT_TABLE_CATALOGS_COLLECTION,
    INDEX_DEFINITIONS,
)
from app.documents.ingestion import IngestionError, IngestionService
from app.documents.models import DocumentStatus, DocumentTableCatalogRecord, TableColumnSchema
from app.documents.repository import RepositoryConflictError, RepositoryError
from app.documents.service import DocumentService
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.infrastructure.s3_storage import S3FileStorage
from tests.integration.test_ingestion import DeterministicEmbeddings, FailingEmbeddings, MemoryRepository
from tests.unit.test_storage_backends import StubS3Client


def _build_multisheet_xlsx() -> bytes:
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Nhân sự"
    ws1.append(["Mã NV", "Họ tên", "Phòng ban", "Lương (Triệu)"])
    ws1.append(["NV001", "Nguyễn Minh Anh", "Kỹ thuật", 25])
    ws1.append(["NV002", "Trần Quốc Bảo", "Nhân sự", 18])

    ws2 = wb.create_sheet("Phòng Ban")
    ws2.append(["Mã PB", "Tên Phòng Ban", "Ngân sách"])
    ws2.append(["PB01", "Kỹ thuật", 500.5])
    ws2.append(["PB02", "Nhân sự", 220.0])

    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


class CatalogMemoryRepository(MemoryRepository):
    """Mở rộng MemoryRepository hỗ trợ table_catalogs giống MongoDocumentRepository."""

    def __init__(self) -> None:
        super().__init__()
        self.table_catalogs: dict[str, list[DocumentTableCatalogRecord]] = {}
        self.fail_catalog_replace_once = False

    def get_job(self, job_id: str):
        return self.jobs[job_id]

    def replace_version_tables(self, version_id: str, records: list[DocumentTableCatalogRecord]) -> None:
        if self.fail_catalog_replace_once:
            self.fail_catalog_replace_once = False
            raise RepositoryError("simulated catalog write failure")
        seen: set[str] = set()
        for item in records:
            if item.version_id != version_id:
                raise RepositoryError("version_id mismatch")
            if item.table_name in seen:
                raise RepositoryConflictError("duplicate table_name")
            seen.add(item.table_name)
        self.table_catalogs[version_id] = list(records)

    def list_tables_for_versions(
        self,
        version_ids: list[str],
        *,
        tenant_id: str | None = None,
    ) -> list[DocumentTableCatalogRecord]:
        result: list[DocumentTableCatalogRecord] = []
        for vid in version_ids:
            for item in self.table_catalogs.get(vid, []):
                if tenant_id is None or item.tenant_id == tenant_id:
                    result.append(item)
        result.sort(key=lambda r: (r.version_id, r.table_name))
        return result

    def delete_tables_for_version(self, version_id: str) -> int:
        removed = self.table_catalogs.pop(version_id, [])
        return len(removed)


class ExcelParquetIngestionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.s3_stub = StubS3Client()
        self.s3_storage = S3FileStorage(bucket="rag-parquet-test-bucket", client=self.s3_stub)
        self.repository = CatalogMemoryRepository()
        self.qdrant = QdrantClient(":memory:")
        self.vector_index = QdrantVectorIndex(self.qdrant, "test_excel_parquet_catalog")

    def tearDown(self) -> None:
        self.qdrant.close()

    def _make_service(
        self,
        *,
        parquet_enabled: bool = True,
        sample_rows: int = 3,
        embeddings=None,
    ) -> DocumentService:
        ingestion = IngestionService(
            repository=self.repository,
            storage=self.s3_storage,
            vector_index=self.vector_index,
            embeddings=embeddings or DeterministicEmbeddings(),
            parquet_ingestion_enabled=parquet_enabled,
            catalog_sample_rows=sample_rows,
        )
        return DocumentService(
            repository=self.repository,
            storage=self.s3_storage,
            vector_index=self.vector_index,
            ingestion=ingestion,
        )

    def test_multisheet_and_hr_employees_mock_write_parquet_and_catalog_accurately(self) -> None:
        service = self._make_service(parquet_enabled=True, sample_rows=3)

        # 1. Test multi-sheet workbook
        multi_res = service.ingestion.ingest(
            file_name="company_hr.xlsx",
            content=_build_multisheet_xlsx(),
            tenant_id="default",
        )
        self.assertEqual(multi_res.status, DocumentStatus.INDEXED)
        catalogs = self.repository.list_tables_for_versions([multi_res.version_id])
        self.assertEqual([c.table_name for c in catalogs], ["nhan_su", "phong_ban"])

        expected_ns_key = f"default/{multi_res.document_id}/v1/tables/nhan_su.parquet"
        expected_pb_key = f"default/{multi_res.document_id}/v1/tables/phong_ban.parquet"
        self.assertEqual(catalogs[0].parquet_key, expected_ns_key)
        self.assertEqual(catalogs[1].parquet_key, expected_pb_key)
        self.assertTrue(self.s3_storage.exists(expected_ns_key))
        self.assertTrue(self.s3_storage.exists(expected_pb_key))

        pa_ns = pq.read_table(io.BytesIO(self.s3_storage.get(expected_ns_key)))
        self.assertEqual(pa_ns.num_rows, 2)
        self.assertEqual(pa_ns.column_names, ["ma_nv", "ho_ten", "phong_ban", "luong_trieu"])
        self.assertEqual(pa_ns.to_pydict()["luong_trieu"], [25, 18])

        # 2. Test data/hr_employees_mock.xlsx
        mock_xlsx_path = Path(__file__).resolve().parents[3] / "data" / "hr_employees_mock.xlsx"
        self.assertTrue(mock_xlsx_path.is_file())
        mock_res = service.ingestion.ingest(
            file_name="hr_employees_mock.xlsx",
            content=mock_xlsx_path.read_bytes(),
            tenant_id="default",
        )
        mock_catalogs = self.repository.list_tables_for_versions([mock_res.version_id])
        self.assertEqual(len(mock_catalogs), 1)
        mock_cat = mock_catalogs[0]
        self.assertEqual(mock_cat.table_name, "nhansu")
        self.assertEqual(mock_cat.sheet_name, "NhanSu")
        self.assertEqual(mock_cat.row_count, 10)
        self.assertEqual(len(mock_cat.sample_rows), 3)

        pa_mock = pq.read_table(io.BytesIO(self.s3_storage.get(mock_cat.parquet_key)))
        self.assertEqual(pa_mock.num_rows, 10)
        self.assertEqual(len(pa_mock.column_names), 10)

    def test_flag_disabled_skips_parquet_and_catalog_while_keeping_rag_chunks(self) -> None:
        service = self._make_service(parquet_enabled=False)
        res = service.ingestion.ingest(
            file_name="flag_off.xlsx",
            content=_build_multisheet_xlsx(),
            tenant_id="default",
        )
        self.assertEqual(res.status, DocumentStatus.INDEXED)
        self.assertGreater(res.num_chunks, 0)
        self.assertEqual(self.repository.list_tables_for_versions([res.version_id]), [])
        parquet_keys = [k for k in self.s3_stub.objects if k.endswith(".parquet")]
        self.assertEqual(parquet_keys, [])

    def test_retry_is_idempotent_and_cleans_stale_parquet_and_catalog(self) -> None:
        failing_service = self._make_service(
            parquet_enabled=True,
            embeddings=FailingEmbeddings(),
        )
        with self.assertRaises(IngestionError) as ctx:
            failing_service.ingestion.ingest(
                file_name="retry_excel.xlsx",
                content=_build_multisheet_xlsx(),
            )
        self.assertEqual(ctx.exception.code, "embedding_failed")
        failed_version = next(iter(self.repository.versions.values()))
        self.assertEqual(failed_version.status, DocumentStatus.FAILED)

        # _fail_before_activation đã dọn sạch Parquet và catalog của version FAILED
        self.assertEqual(
            self.repository.list_tables_for_versions([failed_version.version_id]),
            [],
        )
        self.assertEqual([k for k in self.s3_stub.objects if k.endswith(".parquet")], [])

        # Giả lập có file Parquet rác trước khi retry để xác nhận delete_prefix dọn sạch
        stale_key = f"default/{failed_version.document_id}/v1/tables/stale_orphan.parquet"
        self.s3_storage.put(stale_key, b"orphan-parquet")
        self.assertTrue(self.s3_storage.exists(stale_key))

        working_service = self._make_service(
            parquet_enabled=True,
            embeddings=DeterministicEmbeddings(),
        )
        retried = working_service.ingestion.retry(failed_version.version_id)
        self.assertEqual(retried.status, DocumentStatus.INDEXED)
        self.assertFalse(self.s3_storage.exists(stale_key))

        catalogs = self.repository.list_tables_for_versions([failed_version.version_id])
        self.assertEqual([c.table_name for c in catalogs], ["nhan_su", "phong_ban"])

    def test_failed_v2_preserves_v1_active_parquet_and_catalog_untouched(self) -> None:
        service = self._make_service(parquet_enabled=True)
        v1 = service.ingestion.ingest(
            file_name="budget.xlsx",
            content=_build_multisheet_xlsx(),
        )
        v1_catalogs = self.repository.list_tables_for_versions([v1.version_id])
        self.assertEqual(len(v1_catalogs), 2)

        # Upload v2 nhưng giả lập lỗi ghi catalog -> v2 phải FAIL và cleanup, v1 giữ nguyên
        self.repository.fail_catalog_replace_once = True
        with self.assertRaises(IngestionError) as ctx:
            service.update(
                v1.document_id,
                file_name="budget_v2.xlsx",
                content=_build_multisheet_xlsx(),
            )
        self.assertEqual(ctx.exception.code, "catalog_persistence_failed")

        doc = self.repository.get_document(v1.document_id)
        self.assertEqual(doc.active_version_id, v1.version_id)
        self.assertEqual(len(self.repository.list_tables_for_versions([v1.version_id])), 2)
        for cat in v1_catalogs:
            self.assertTrue(self.s3_storage.exists(cat.parquet_key))

        v2_parquet_keys = [
            k for k in self.s3_stub.objects if f"/{v1.document_id}/v2/tables/" in k
        ]
        self.assertEqual(v2_parquet_keys, [])

    def test_reindex_generates_parquet_and_catalog_when_flag_enabled(self) -> None:
        # Bước 1: Ingest v1 khi cờ tắt
        service_off = self._make_service(parquet_enabled=False)
        v1 = service_off.ingestion.ingest(
            file_name="legacy_no_parquet.xlsx",
            content=_build_multisheet_xlsx(),
        )
        self.assertEqual(self.repository.list_tables_for_versions([v1.version_id]), [])

        # Bước 2: Bật cờ và gọi reindex -> sinh v2 có đầy đủ Parquet + catalog
        service_on = self._make_service(parquet_enabled=True)
        v2 = service_on.reindex(v1.document_id)
        self.assertEqual(v2.status, DocumentStatus.INDEXED)
        v2_catalogs = self.repository.list_tables_for_versions([v2.version_id])
        self.assertEqual([c.table_name for c in v2_catalogs], ["nhan_su", "phong_ban"])
        for cat in v2_catalogs:
            self.assertTrue(self.s3_storage.exists(cat.parquet_key))

    def test_table_catalog_index_definitions_include_unique_version_table_index(self) -> None:
        self.assertIn(DOCUMENT_TABLE_CATALOGS_COLLECTION, INDEX_DEFINITIONS)
        index_specs = INDEX_DEFINITIONS[DOCUMENT_TABLE_CATALOGS_COLLECTION]
        names = {spec.document["name"] for spec in index_specs}
        self.assertIn("uq_document_table_catalogs_version_table", names)
        self.assertIn("idx_document_table_catalogs_tenant_doc_version", names)

        rec = DocumentTableCatalogRecord(
            tenant_id="default",
            document_id=str(uuid4()),
            version_id=str(uuid4()),
            table_name="nhan_su",
            sheet_name="Nhân sự",
            parquet_key="default/doc/v1/tables/nhan_su.parquet",
            row_count=10,
            columns=[
                TableColumnSchema(
                    name="ma_nv",
                    original_name="Mã NV",
                    type="VARCHAR",
                    nullable=False,
                    description="Cột 'Mã NV' (kiểu VARCHAR)",
                )
            ],
            sample_rows=[{"ma_nv": "NV001"}],
        )
        mongo_doc = rec.to_mongo()
        self.assertEqual(mongo_doc["_id"], rec.catalog_id)
        restored = DocumentTableCatalogRecord.model_validate(mongo_doc)
        self.assertEqual(restored.columns[0].type, "VARCHAR")


if __name__ == "__main__":
    unittest.main()
