"""Unit tests cho T4.2: phân loại cột `is_free_text`, selective embedding Excel, hỗ trợ 0 chunk và validate cờ cấu hình."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from io import BytesIO
from pathlib import Path
import unittest

from langchain_core.embeddings import Embeddings
from openpyxl import Workbook
from pydantic import ValidationError
from qdrant_client import QdrantClient

from app.documents.excel.tabular import (
    classify_free_text_column,
    extract_workbook_tables,
)
from app.documents.ingestion import IngestionError, IngestionService
from app.documents.models import (
    DocumentStatus,
    IngestionJobStatus,
    utc_now,
)
from app.documents.ports import FileStorage, StorageNotFoundError, StoredFile
from app.documents.service import DocumentService
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.rag.loaders.excel import workbook_documents
from app.rag.vector_index import VectorFilter
from app.shared.config import Settings


def _build_xlsx_bytes(sheets: dict[str, list[list[object]]]) -> bytes:
    wb = Workbook()
    first = True
    for title, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = title
            first = False
        else:
            ws = wb.create_sheet(title=title)
        for row in rows:
            ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


class SpyEmbeddings(Embeddings):
    def __init__(self) -> None:
        self.call_count = 0
        self.embedded_texts: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.embedded_texts.extend(texts)
        return [[float(len(t)), 1.0, 0.5] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.5]


class MemoryCatalogRepository:
    """In-memory repository hỗ trợ đầy đủ lifecycle + table catalog cho unit tests."""

    def __init__(self) -> None:
        self.documents: dict[str, object] = {}
        self.versions: dict[str, object] = {}
        self.jobs: dict[str, object] = {}
        self.catalogs: dict[str, list[object]] = {}
        self.fail_finalize_once = False

    def create_upload(self, document, version, job) -> None:
        self.documents[document.document_id] = document
        self.versions[version.version_id] = version
        self.jobs[job.job_id] = job

    def create_version_upload(self, version, job) -> None:
        self.versions[version.version_id] = version
        self.jobs[job.job_id] = job

    def get_document(self, document_id: str):
        return self.documents[document_id]

    def get_version(self, version_id: str):
        return self.versions[version_id]

    def get_job(self, job_id: str):
        return self.jobs[job_id]

    def list_documents(self, *, include_deleted: bool = False, offset: int = 0, limit: int = 100):
        values = sorted(self.documents.values(), key=lambda d: d.created_at, reverse=True)
        if not include_deleted:
            values = [d for d in values if d.status != DocumentStatus.DELETED]
        return values[offset : offset + limit]

    def list_versions(self, document_id: str):
        return sorted(
            (v for v in self.versions.values() if v.document_id == document_id),
            key=lambda v: v.version,
            reverse=True,
        )

    def next_version_number(self, document_id: str) -> int:
        nums = [v.version for v in self.versions.values() if v.document_id == document_id]
        return max(nums, default=0) + 1

    def mark_processing(self, document_id: str, version_id: str, job_id: str) -> None:
        now = utc_now()
        self.versions[version_id] = self.versions[version_id].model_copy(
            update={"status": DocumentStatus.PROCESSING, "updated_at": now}
        )
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={"status": IngestionJobStatus.PROCESSING, "started_at": now, "updated_at": now}
        )
        doc = self.documents[document_id]
        if doc.active_version_id is None:
            self.documents[document_id] = doc.model_copy(
                update={"status": DocumentStatus.PROCESSING, "updated_at": now}
            )

    def set_chunk_plan(
        self,
        version_id: str,
        *,
        chunk_count: int,
        embedding_model: str,
        vector_collection: str,
    ) -> None:
        self.versions[version_id] = self.versions[version_id].model_copy(
            update={
                "chunk_count": chunk_count,
                "embedding_model": embedding_model,
                "vector_collection": vector_collection,
                "updated_at": utc_now(),
            }
        )

    def complete_and_activate(self, version_id: str, job_id: str) -> bool:
        if self.fail_finalize_once:
            self.fail_finalize_once = False
            from app.documents.repository import RepositoryError

            raise RepositoryError("simulated finalize failure")
        now = utc_now()
        version = self.versions[version_id].model_copy(
            update={"status": DocumentStatus.INDEXED, "indexed_at": now, "updated_at": now}
        )
        self.versions[version_id] = version
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={
                "status": IngestionJobStatus.COMPLETED,
                "error_code": None,
                "completed_at": now,
                "updated_at": now,
            }
        )
        doc = self.documents[version.document_id]
        self.documents[version.document_id] = doc.model_copy(
            update={
                "status": DocumentStatus.INDEXED,
                "active_version_id": version_id,
                "updated_at": now,
            }
        )
        return True

    def mark_failed(self, document_id: str, version_id: str, job_id: str, error_code: str) -> None:
        now = utc_now()
        self.versions[version_id] = self.versions[version_id].model_copy(
            update={"status": DocumentStatus.FAILED, "updated_at": now}
        )
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={
                "status": IngestionJobStatus.FAILED,
                "error_code": error_code,
                "completed_at": now,
                "updated_at": now,
            }
        )
        doc = self.documents[document_id]
        if doc.active_version_id is None and doc.status != DocumentStatus.DELETED:
            self.documents[document_id] = doc.model_copy(
                update={"status": DocumentStatus.FAILED, "updated_at": now}
            )

    def is_active_version(self, document_id: str, version_id: str) -> bool:
        return self.documents[document_id].active_version_id == version_id

    def is_document_deleted(self, document_id: str) -> bool:
        return self.documents[document_id].status == DocumentStatus.DELETED

    def latest_processing_job(self, version_id: str):
        jobs = [
            j
            for j in self.jobs.values()
            if j.version_id == version_id and j.status == IngestionJobStatus.PROCESSING
        ]
        return max(jobs, key=lambda j: j.attempt)

    def list_processing_versions(self, limit: int = 100):
        values = [
            v
            for v in self.versions.values()
            if v.status in {DocumentStatus.PROCESSING, DocumentStatus.INDEXED}
            and (v.chunk_count > 0 or v.vector_collection is not None)
            and any(
                j.version_id == v.version_id and j.status == IngestionJobStatus.PROCESSING
                for j in self.jobs.values()
            )
        ]
        return values[:limit]

    def replace_version_tables(self, version_id: str, records) -> None:
        self.catalogs[version_id] = list(records)

    def list_tables_for_versions(self, version_ids, *, tenant_id: str | None = None):
        out = []
        for vid in version_ids:
            for item in self.catalogs.get(vid, []):
                if tenant_id is None or item.tenant_id == tenant_id:
                    out.append(item)
        return out

    def delete_tables_for_version(self, version_id: str) -> int:
        removed = len(self.catalogs.pop(version_id, []))
        return removed


class InMemoryFileStorage(FileStorage):
    backend_name = "s3"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredFile:
        self.objects[key] = bytes(data)
        return StoredFile(
            storage_key=key,
            size_bytes=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
        )

    def save(self, storage_key: str, content: bytes) -> StoredFile:
        return self.put(storage_key, content)

    def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise StorageNotFoundError(key)
        return self.objects[key]

    def read(self, storage_key: str) -> bytes:
        return self.get(storage_key)

    @contextmanager
    def open(self, storage_key: str):
        yield BytesIO(self.get(storage_key))

    def exists(self, storage_key: str) -> bool:
        return storage_key in self.objects

    def delete(self, storage_key: str) -> None:
        self.objects.pop(storage_key, None)

    def delete_prefix(self, prefix: str) -> int:
        matched = [k for k in self.objects if k.startswith(prefix)]
        for k in matched:
            self.objects.pop(k, None)
        return len(matched)


class ExcelSelectiveEmbeddingUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = InMemoryFileStorage()
        self.repository = MemoryCatalogRepository()
        self.qdrant = QdrantClient(":memory:")
        self.vector_index = QdrantVectorIndex(self.qdrant, "test_selective_excel")

    def tearDown(self) -> None:
        self.qdrant.close()

    def test_column_classification_distinguishes_free_text_from_numbers_ids_categories_and_sensitive(
        self,
    ) -> None:
        self.assertFalse(
            classify_free_text_column(
                name="so_luong",
                original_name="Số lượng",
                data_type="INT64",
                values=[10, 20, 30],
            )
        )
        self.assertFalse(
            classify_free_text_column(
                name="ma_nhan_vien",
                original_name="Mã nhân viên",
                data_type="VARCHAR",
                values=["EMP001", "EMP002", "EMP003", "EMP004"],
            )
        )
        self.assertFalse(
            classify_free_text_column(
                name="phong_ban",
                original_name="Phòng ban",
                data_type="VARCHAR",
                values=["Kỹ thuật", "Nhân sự", "Kỹ thuật", "Tài chính", "Nhân sự"],
            )
        )
        # Cột nhạy cảm dù dài nhiều từ (ví dụ Địa chỉ thường trú) vẫn bị loại khỏi is_free_text
        self.assertFalse(
            classify_free_text_column(
                name="dia_chi_thuong_tru",
                original_name="Địa chỉ thường trú",
                data_type="VARCHAR",
                values=[
                    "Số 123 đường Nguyễn Trãi, Phường Bến Thành, Quận 1, TP Hồ Chí Minh",
                    "Số 456 đường Lê Lợi, Phường Hải Châu 1, Quận Hải Châu, TP Đà Nẵng",
                ],
            )
        )
        self.assertFalse(
            classify_free_text_column(
                name="ghi_chu_luong",
                original_name="Ghi chú lương thưởng",
                data_type="VARCHAR",
                values=[
                    "Thưởng hiệu suất quý 1 theo mức lương cơ bản mới đã phê duyệt",
                    "Điều chỉnh phụ cấp trách nhiệm và thưởng dự án cuối năm",
                ],
            )
        )
        # Cột ghi chú đánh giá dài không nhạy cảm -> is_free_text = True
        self.assertTrue(
            classify_free_text_column(
                name="nhan_xet_danh_gia",
                original_name="Nhận xét đánh giá",
                data_type="VARCHAR",
                values=[
                    "Nhân viên hoàn thành xuất sắc mục tiêu chuyển đổi số và hỗ trợ đồng đội tốt.",
                    "Cần tăng cường kỹ năng viết tài liệu thiết kế hệ thống và kiểm thử tự động.",
                    "Chủ động xử lý sự cố sản xuất và phối hợp hiệu quả với nhóm vận hành.",
                ],
            )
        )

    def test_workbook_documents_text_only_embeds_only_free_text_and_skips_empty_rows(
        self,
    ) -> None:
        xlsx_bytes = _build_xlsx_bytes(
            {
                "NhanSu": [
                    ["Mã NV", "Phòng ban", "Lương cơ bản", "Nhận xét đánh giá"],
                    [
                        "NV01",
                        "Kỹ thuật",
                        25000000,
                        "Hoàn thành xuất sắc kiến trúc microservices và hướng dẫn thành viên mới trong nhóm.",
                    ],
                    [
                        "NV02",
                        "Nhân sự",
                        18000000,
                        "",
                    ],
                    [
                        "NV03",
                        "Tài chính",
                        22000000,
                        "Thực hiện kiểm toán nội bộ chính xác, đề xuất quy trình tối ưu chi phí vận hành.",
                    ],
                ],
                "BangSoThuan": [
                    ["Tháng", "Doanh thu", "Chi phí"],
                    [1, 1000000, 600000],
                    [2, 1200000, 700000],
                ],
            }
        )

        tables = extract_workbook_tables(xlsx_bytes)
        self.assertEqual(len(tables), 2)
        nhansu_cols = {c.name: c.is_free_text for c in tables[0].columns}
        self.assertEqual(
            nhansu_cols,
            {
                "ma_nv": False,
                "phong_ban": False,
                "luong_co_ban": False,
                "nhan_xet_danh_gia": True,
            },
        )
        self.assertTrue(all(not c.is_free_text for c in tables[1].columns))

        from app.shared.config import settings

        prev = settings.excel_text_only_embedding_enabled
        try:
            settings.excel_text_only_embedding_enabled = False
            legacy_docs = workbook_documents(xlsx_bytes)
            self.assertEqual(len(legacy_docs), 5)

            settings.excel_text_only_embedding_enabled = True
            selective_docs = workbook_documents(xlsx_bytes)
            self.assertEqual(len(selective_docs), 2)
            self.assertIn("NV01", selective_docs[0].page_content)
            self.assertIn("microservices", selective_docs[0].page_content)
            self.assertNotIn("25000000", selective_docs[0].page_content)
            self.assertNotIn("Kỹ thuật", selective_docs[0].page_content)
            self.assertEqual(selective_docs[0].metadata["sheet_name"], "NhanSu")
            self.assertEqual(selective_docs[0].metadata["row_index"], 2)
            self.assertEqual(selective_docs[1].metadata["row_index"], 4)
        finally:
            settings.excel_text_only_embedding_enabled = prev

    def test_pure_numeric_excel_succeeds_with_zero_chunks_and_zero_embedding_calls(
        self,
    ) -> None:
        pure_numeric_xlsx = _build_xlsx_bytes(
            {
                "DoanhThu": [
                    ["Mã ĐH", "Số lượng", "Đơn giá", "Thành tiền"],
                    ["DH001", 10, 150000, 1500000],
                    ["DH002", 5, 200000, 1000000],
                    ["DH003", 8, 125000, 1000000],
                ]
            }
        )
        spy_embeddings = SpyEmbeddings()
        service = IngestionService(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            embeddings=spy_embeddings,
            parquet_ingestion_enabled=True,
            text_only_embedding_enabled=True,
        )

        result = service.ingest(file_name="doanh_thu.xlsx", content=pure_numeric_xlsx)
        self.assertTrue(result.activated)
        self.assertEqual(result.num_chunks, 0)
        self.assertEqual(spy_embeddings.call_count, 0)

        doc = self.repository.get_document(result.document_id)
        version = self.repository.get_version(result.version_id)
        self.assertEqual(doc.status, DocumentStatus.INDEXED)
        self.assertEqual(version.status, DocumentStatus.INDEXED)
        self.assertEqual(version.chunk_count, 0)
        self.assertEqual(
            self.vector_index.count(VectorFilter(version_id=result.version_id)),
            0,
        )
        catalogs = self.repository.list_tables_for_versions([result.version_id])
        self.assertEqual(len(catalogs), 1)
        self.assertEqual(catalogs[0].row_count, 3)

    def test_zero_chunk_reconciliation_and_non_excel_empty_chunks_rejection(self) -> None:
        pure_numeric_xlsx = _build_xlsx_bytes(
            {
                "ChiPhi": [
                    ["Tháng", "Chi phí vận hành"],
                    [1, 5000000],
                    [2, 6200000],
                ]
            }
        )
        spy_embeddings = SpyEmbeddings()
        service = IngestionService(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            embeddings=spy_embeddings,
            parquet_ingestion_enabled=True,
            text_only_embedding_enabled=True,
        )

        self.repository.fail_finalize_once = True
        with self.assertRaises(IngestionError) as ctx:
            service.ingest(file_name="chi_phi.xlsx", content=pure_numeric_xlsx)
        self.assertEqual(ctx.exception.code, "metadata_finalize_failed")

        summary = service.reconcile_processing()
        self.assertEqual(summary, {"completed": 1, "failed": 0, "skipped": 0})

        # File .txt hoặc .md rỗng (0 chunk) vẫn phải bị chặn với empty_chunks
        with self.assertRaises(IngestionError) as txt_ctx:
            service.ingest(file_name="empty.txt", content=b"   \n  ")
        self.assertEqual(txt_ctx.exception.code, "empty_chunks")

    def test_reindex_from_legacy_to_text_only_cleans_up_old_qdrant_vectors(self) -> None:
        pure_numeric_xlsx = _build_xlsx_bytes(
            {
                "ThongKe": [
                    ["Mã SP", "Số lượng tồn", "Giá nhập"],
                    ["SP01", 100, 50000],
                    ["SP02", 250, 75000],
                ]
            }
        )
        spy_embeddings = SpyEmbeddings()
        legacy_ingestion = IngestionService(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            embeddings=spy_embeddings,
            parquet_ingestion_enabled=True,
            text_only_embedding_enabled=False,
        )
        v1 = legacy_ingestion.ingest(file_name="ton_kho.xlsx", content=pure_numeric_xlsx)
        self.assertGreater(v1.num_chunks, 0)
        self.assertEqual(
            self.vector_index.count(VectorFilter(document_id=v1.document_id)),
            v1.num_chunks,
        )

        # Chuyển sang chế độ text-only và chạy reindex -> v2 có 0 chunk, điểm Qdrant của v1 được dọn sạch
        text_only_ingestion = IngestionService(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            embeddings=spy_embeddings,
            parquet_ingestion_enabled=True,
            text_only_embedding_enabled=True,
        )
        doc_service = DocumentService(
            repository=self.repository,
            storage=self.storage,
            vector_index=self.vector_index,
            ingestion=text_only_ingestion,
        )
        calls_before_reindex = spy_embeddings.call_count
        v2 = doc_service.reindex(v1.document_id)
        self.assertTrue(v2.activated)
        self.assertEqual(v2.num_chunks, 0)
        self.assertEqual(spy_embeddings.call_count, calls_before_reindex)
        self.assertEqual(
            self.vector_index.count(VectorFilter(document_id=v1.document_id)),
            0,
        )

    def test_settings_cross_flag_validation_names_missing_flags(self) -> None:
        with self.assertRaises(ValidationError) as sql_ctx:
            Settings(
                _env_file=None,
                groq_api_key="gsk_test",
                embedding_api_key="AIza_test",
                excel_sql_enabled=True,
                agentic_mode_enabled=False,
                storage_backend="local",
                excel_parquet_ingestion_enabled=False,
            )
        msg = str(sql_ctx.exception)
        self.assertIn("AGENTIC_MODE_ENABLED=true", msg)
        self.assertIn("STORAGE_BACKEND=s3", msg)
        self.assertIn("EXCEL_PARQUET_INGESTION_ENABLED=true", msg)

        with self.assertRaises(ValidationError) as embed_ctx:
            Settings(
                _env_file=None,
                groq_api_key="gsk_test",
                embedding_api_key="AIza_test",
                excel_text_only_embedding_enabled=True,
                excel_parquet_ingestion_enabled=False,
            )
        self.assertIn("EXCEL_PARQUET_INGESTION_ENABLED=true", str(embed_ctx.exception))


if __name__ == "__main__":
    unittest.main()
