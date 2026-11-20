"""Integration & RBAC tests cho Giai đoạn 3 (T3.4 & T3.5): ExcelSqlService + DuckDBSqlExecutor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import io
import json
import unittest

from openpyxl import Workbook
from qdrant_client import QdrantClient

from app.documents.excel.sql_service import (
    ExcelSqlService,
    create_run_sql_handler,
    run_sql_tool_definition,
)
from app.documents.ingestion import IngestionService
from app.documents.models import DocumentStatus
from app.documents.service import DocumentService
from app.infrastructure.duckdb_executor import DuckDBSqlExecutor
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.infrastructure.s3_storage import S3FileStorage
from app.shared.auth import UserContext
from tests.integration.test_excel_parquet_ingestion import CatalogMemoryRepository
from tests.integration.test_ingestion import DeterministicEmbeddings
from tests.unit.test_storage_backends import StubS3Client


@dataclass(frozen=True)
class FakeSessionScope:
    mode: str = "ALL_ACTIVE"
    document_ids: tuple[str, ...] = ()


def _build_hr_xlsx(sheet_title: str, rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(["MaNV", "HoTen", "PhongBan", "Luong", "NgayVao"])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


class RunSqlRbacIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.s3_stub = StubS3Client()
        self.s3_storage = S3FileStorage(bucket="rag-rbac-test-bucket", client=self.s3_stub)
        self.repository = CatalogMemoryRepository()
        self.qdrant = QdrantClient(":memory:")
        self.vector_index = QdrantVectorIndex(self.qdrant, "test_run_sql_rbac")

        self.ingestion = IngestionService(
            repository=self.repository,
            storage=self.s3_storage,
            vector_index=self.vector_index,
            embeddings=DeterministicEmbeddings(),
            parquet_ingestion_enabled=True,
        )
        self.doc_service = DocumentService(
            repository=self.repository,
            storage=self.s3_storage,
            vector_index=self.vector_index,
            ingestion=self.ingestion,
        )
        self.executor = DuckDBSqlExecutor(
            storage_backend="s3",
            s3_bucket="rag-rbac-test-bucket",
            query_access_key_id="AKIA_QUERY_ONLY",
            query_secret_access_key="SECRET_QUERY_ONLY",
            ingest_access_key_id="AKIA_INGEST_WRITE",
            _test_parquet_bytes_by_key=self.s3_stub.objects,
        )
        self.sql_service = ExcelSqlService(
            repository=self.repository,
            executor=self.executor,
            max_rows=200,
        )

    def tearDown(self) -> None:
        self.qdrant.close()

    def test_run_sql_contract_forbids_extra_identity_parameters_from_llm(self) -> None:
        definition = run_sql_tool_definition()
        self.assertEqual(definition.name, "run_sql")
        schema = definition.input_schema()
        self.assertEqual(set(schema.get("properties", {}).keys()), {"sql"})

        handler = create_run_sql_handler(
            self.sql_service,
            user=UserContext(user_id="u1", username="alice", tenant_id="default"),
        )
        for forbidden_field in ("user_id", "tenant_id", "s3_path", "document_id"):
            env = handler({"sql": "SELECT 1", forbidden_field: "injected"})
            self.assertFalse(env["ok"])
            self.assertEqual(env["error"]["code"], "TOOL_INVALID_ARGUMENTS")

    def test_rbac_blocks_cross_tenant_unpermitted_user_deleted_unindexed_old_version_and_out_of_scope(self) -> None:
        # 1. Tài liệu thuộc tenant_a, chỉ cho role "hr_manager" hoặc owner "owner-a"
        doc_a = self.ingestion.ingest(
            file_name="hr_tenant_a.xlsx",
            content=_build_hr_xlsx("BangLuong", [
                ["NV01", "Alice", "Kỹ thuật", 30, date(2025, 1, 10)],
                ["NV02", "Bob", "Nhân sự", 20, date(2025, 3, 15)],
            ]),
            tenant_id="tenant_a",
            owner_id="owner-a",
            allowed_roles=["hr_manager"],
        )

        # User thuộc tenant_b -> không thấy bảng của tenant_a
        user_tenant_b = UserContext(
            user_id="owner-a",
            username="alice",
            roles=("hr_manager",),
            tenant_id="tenant_b",
        )
        res_cross_tenant = self.sql_service.execute_query(
            sql="SELECT COUNT(*) AS cnt FROM bangluong",
            user=user_tenant_b,
        )
        self.assertTrue(res_cross_tenant["ok"])
        self.assertEqual(res_cross_tenant["data"]["status"], "NO_TABLES_AVAILABLE")

        # User cùng tenant_a nhưng chỉ có role "viewer" và không phải owner -> không có quyền
        user_unpermitted = UserContext(
            user_id="guest-1",
            username="guest",
            roles=("viewer",),
            tenant_id="tenant_a",
        )
        res_unpermitted = self.sql_service.execute_query(
            sql="SELECT COUNT(*) AS cnt FROM bangluong",
            user=user_unpermitted,
        )
        self.assertTrue(res_unpermitted["ok"])
        self.assertEqual(res_unpermitted["data"]["status"], "NO_TABLES_AVAILABLE")

        # User hợp lệ (role hr_manager trong tenant_a) -> truy vấn thành công v1 (tổng lương = 50)
        user_authorized = UserContext(
            user_id="manager-1",
            username="manager",
            roles=("hr_manager",),
            tenant_id="tenant_a",
        )
        res_v1 = self.sql_service.execute_query(
            sql="SELECT SUM(luong) AS tong_luong FROM bangluong",
            user=user_authorized,
        )
        self.assertTrue(res_v1["ok"])
        self.assertEqual(res_v1["data"]["rows"], [{"tong_luong": 50}])

        # 2. Upload v2 (tổng lương = 100) -> chỉ v2 active được phép truy vấn, v1 cũ bị loại
        self.doc_service.update(
            doc_a.document_id,
            file_name="hr_tenant_a_v2.xlsx",
            content=_build_hr_xlsx("BangLuong", [
                ["NV01", "Alice", "Kỹ thuật", 100, date(2025, 1, 10)],
            ]),
        )
        res_v2 = self.sql_service.execute_query(
            sql="SELECT SUM(luong) AS tong_luong FROM bangluong",
            user=user_authorized,
        )
        self.assertTrue(res_v2["ok"])
        self.assertEqual(res_v2["data"]["rows"], [{"tong_luong": 100}])

        # 3. Tạo 1 tài liệu ở trạng thái UPLOADED (chưa INDEXED) -> không được phép truy vấn
        unindexed = self.ingestion.prepare_ingest(
            file_name="pending.xlsx",
            content=_build_hr_xlsx("PendingSheet", [
                ["NV99", "Pending", "IT", 999, date(2026, 1, 1)],
            ]),
            tenant_id="tenant_a",
            owner_id="manager-1",
        )
        tables_for_auth = self.sql_service.list_authorized_tables(user=user_authorized)
        self.assertEqual([t.document_id for t in tables_for_auth], [doc_a.document_id])
        self.assertNotIn(unindexed.document_id, [t.document_id for t in tables_for_auth])

        # 4. SessionScope SELECTED_DOCUMENTS không chứa doc_a -> không được phép truy vấn doc_a
        out_of_scope = FakeSessionScope(
            mode="SELECTED_DOCUMENTS",
            document_ids=(unindexed.document_id,),
        )
        res_scoped_out = self.sql_service.execute_query(
            sql="SELECT * FROM bangluong",
            user=user_authorized,
            session_scope=out_of_scope,
        )
        self.assertTrue(res_scoped_out["ok"])
        self.assertEqual(res_scoped_out["data"]["status"], "NO_TABLES_AVAILABLE")

        # 5. Xóa (unpublish/DELETED) doc_a -> không còn truy vấn được
        self.doc_service.delete(doc_a.document_id)
        res_deleted = self.sql_service.execute_query(
            sql="SELECT * FROM bangluong",
            user=user_authorized,
        )
        self.assertTrue(res_deleted["ok"])
        self.assertEqual(res_deleted["data"]["status"], "NO_TABLES_AVAILABLE")

    def test_two_files_with_same_sheet_name_get_deterministic_non_colliding_aliases_and_can_join(self) -> None:
        user = UserContext(user_id="hr-1", username="hr", tenant_id="default")
        doc1 = self.ingestion.ingest(
            file_name="branch_hanoi.xlsx",
            content=_build_hr_xlsx("NhanSu", [
                ["NV01", "Nguyễn Hà Nội", "Kỹ thuật", 25, date(2025, 2, 1)],
            ]),
            tenant_id="default",
            owner_id="hr-1",
        )
        doc2 = self.ingestion.ingest(
            file_name="branch_hcm.xlsx",
            content=_build_hr_xlsx("NhanSu", [
                ["NV02", "Trần Sài Gòn", "Kỹ thuật", 35, date(2025, 4, 1)],
            ]),
            tenant_id="default",
            owner_id="hr-1",
        )

        bindings_first = self.sql_service.list_authorized_tables(user=user)
        bindings_second = self.sql_service.list_authorized_tables(user=user)
        self.assertEqual(len(bindings_first), 2)
        self.assertEqual(
            [b.view_name for b in bindings_first],
            [b.view_name for b in bindings_second],
        )
        self.assertNotEqual(bindings_first[0].view_name, bindings_first[1].view_name)
        self.assertIn(doc1.document_id.replace("-", "")[:8], {b.view_name[-8:] for b in bindings_first})
        self.assertIn(doc2.document_id.replace("-", "")[:8], {b.view_name[-8:] for b in bindings_first})

        v1_alias = bindings_first[0].view_name
        v2_alias = bindings_first[1].view_name
        join_res = self.sql_service.execute_query(
            sql=(
                f"SELECT a.hoten AS hn_Or_hcm_1, b.hoten AS hn_or_hcm_2, (a.luong + b.luong) AS tong "
                f"FROM {v1_alias} a JOIN {v2_alias} b ON a.phongban = b.phongban"
            ),
            user=user,
        )
        self.assertTrue(join_res["ok"])
        self.assertEqual(join_res["data"]["rows"][0]["tong"], 60)
        self.assertEqual(len(join_res["data"]["referenced_tables"]), 2)

    def test_structured_audit_log_records_metadata_without_leaking_row_values_or_credentials(self) -> None:
        user = UserContext(user_id="auditor-1", username="auditor", tenant_id="default")
        self.ingestion.ingest(
            file_name="sensitive_hr.xlsx",
            content=_build_hr_xlsx("NhanSu", [
                ["NV_SECRET_999", "Bí Mật Tuyệt Đối", "Kỹ thuật", 888888, date(2025, 1, 1)],
            ]),
            tenant_id="default",
            owner_id="auditor-1",
        )

        with self.assertLogs("app.documents.excel.sql_service", level="INFO") as cm:
            ok_res = self.sql_service.execute_query(
                sql="SELECT manv, hoten, luong FROM nhansu",
                user=user,
            )
            bad_res = self.sql_service.execute_query(
                sql="SELECT * FROM read_parquet('/etc/passwd')",
                user=user,
            )

        self.assertTrue(ok_res["ok"])
        self.assertFalse(bad_res["ok"])
        self.assertEqual(len(cm.output), 2)

        first_log = cm.output[0]
        second_log = cm.output[1]
        # Tuyệt đối không log dữ liệu hàng trả về hoặc credential
        for log_line in cm.output:
            self.assertNotIn("NV_SECRET_999", log_line)
            self.assertNotIn("Bí Mật Tuyệt Đối", log_line)
            self.assertNotIn("888888", log_line)
            self.assertNotIn("AKIA_QUERY_ONLY", log_line)
            self.assertNotIn("SECRET_QUERY_ONLY", log_line)

        first_json = json.loads(first_log.split("excel_sql_audit ", 1)[1])
        second_json = json.loads(second_log.split("excel_sql_audit ", 1)[1])
        self.assertEqual(first_json["outcome"], "OK")
        self.assertEqual(first_json["user_id"], "auditor-1")
        self.assertEqual(first_json["tenant_id"], "default")
        self.assertEqual(first_json["row_count"], 1)
        self.assertEqual(len(first_json["referenced_documents"]), 1)

        self.assertEqual(second_json["outcome"], "GUARD_REJECTED")
        self.assertEqual(second_json["row_count"], 0)


if __name__ == "__main__":
    unittest.main()
