"""Unit & security tests cho Giai đoạn 3 (T3.3 & T3.5): DuckDBSqlExecutor trên DuckDB thực tế."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

import duckdb
from openpyxl import Workbook

from app.documents.excel.tabular import extract_workbook_tables
from app.documents.ports import (
    AuthorizedSqlTable,
    SqlConfigurationError,
    SqlQueryExecutionError,
    SqlQueryTimeoutError,
)
from app.infrastructure.duckdb_executor import DuckDBSqlExecutor, create_duckdb_sql_executor


def _build_two_sheets_parquet_bytes() -> tuple[bytes, bytes]:
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "NhanSu"
    ws1.append(["MaNV", "HoTen", "PhongBan", "Luong", "MoTaDai"])
    ws1.append(["NV01", "Nguyễn Văn A", "Kỹ thuật", 30, "X" * 1500])
    ws1.append(["NV02", "Trần Thị B", "Kỹ thuật", 20, "Ngắn"])
    ws1.append(["NV03", "Lê Văn C", "Nhân sự", 18, "Ngắn"])
    ws1.append(["NV04", "Phạm Thị D", "Kinh doanh", 22, "Ngắn"])

    ws2 = wb.create_sheet("PhongBan")
    ws2.append(["TenPhongBan", "TruongPhong"])
    ws2.append(["Kỹ thuật", "Minh Anh"])
    ws2.append(["Nhân sự", "Quốc Bảo"])
    ws2.append(["Kinh doanh", "Hoàng Nam"])

    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    tables = extract_workbook_tables(buf.getvalue())
    return tables[0].parquet_bytes, tables[1].parquet_bytes


class DuckDBSqlExecutorUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ns_parquet, self.pb_parquet = _build_two_sheets_parquet_bytes()
        self.ns_key = "default/11111111-1111-4111-8111-111111111111/v1/tables/nhansu.parquet"
        self.pb_key = "default/11111111-1111-4111-8111-111111111111/v1/tables/phongban.parquet"
        self.parquet_map = {
            self.ns_key: self.ns_parquet,
            self.pb_key: self.pb_parquet,
        }
        self.tables = (
            AuthorizedSqlTable(
                view_name="nhansu",
                parquet_key=self.ns_key,
                tenant_id="default",
                columns=("manv", "hoten", "phongban", "luong", "motadai"),
            ),
            AuthorizedSqlTable(
                view_name="phongban",
                parquet_key=self.pb_key,
                tenant_id="default",
                columns=("tenphongban", "truongphong"),
            ),
        )

    def _make_executor(self, **overrides) -> DuckDBSqlExecutor:
        params = {
            "storage_backend": "s3",
            "s3_bucket": "rag-test-s3-bucket",
            "s3_region": "ap-southeast-1",
            "query_access_key_id": "AKIA_READONLY_QUERY",
            "query_secret_access_key": "SECRET_READONLY_QUERY_VALUE",
            "ingest_access_key_id": "AKIA_WRITE_INGEST",
            "memory_limit": "256MB",
            "threads": 2,
            "timeout_seconds": 5.0,
            "max_rows": 200,
            "_test_parquet_bytes_by_key": self.parquet_map,
        }
        params.update(overrides)
        return DuckDBSqlExecutor(**params)

    def test_rejects_non_s3_storage_backend_or_duplicate_ingest_credentials(self) -> None:
        with self.assertRaises(SqlConfigurationError):
            self._make_executor(storage_backend="local")

        with self.assertRaises(SqlConfigurationError):
            self._make_executor(s3_bucket="")

        with self.assertRaises(SqlConfigurationError):
            self._make_executor(query_access_key_id="", query_secret_access_key="")

        # Bắt buộc credential query phải khác credential ingestion
        with self.assertRaises(SqlConfigurationError):
            self._make_executor(
                query_access_key_id="AKIA_SAME_KEY",
                ingest_access_key_id="AKIA_SAME_KEY",
            )

        class LocalSettings:
            storage_backend = "local"
            s3_bucket = "rag-bucket"
            s3_query_access_key_id = "AKIA_Q"
            s3_query_secret_access_key = "SECRET_Q"
            s3_ingest_access_key_id = "AKIA_I"

        with self.assertRaises(SqlConfigurationError):
            create_duckdb_sql_executor(LocalSettings())

    def test_security_lockdown_blocks_setting_mutation_local_files_and_secrets_on_real_duckdb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_parquet_file = Path(tmp_dir) / "local_secret.parquet"
            local_parquet_file.write_bytes(self.ns_parquet)
            posix_local_path = local_parquet_file.as_posix()

            verified_assertions: list[str] = []

            def _verify_after_lockdown(conn: duckdb.DuckDBPyConnection) -> None:
                # 1. Không thể mở khóa hoặc đổi bất kỳ setting nào sau SET lock_configuration = true
                with self.assertRaises(duckdb.Error):
                    conn.execute("SET lock_configuration = false")
                with self.assertRaises(duckdb.Error):
                    conn.execute("SET memory_limit = '2GB'")
                with self.assertRaises(duckdb.Error):
                    conn.execute("SET disabled_filesystems = ''")
                verified_assertions.append("settings_locked")

                # 2. Không thể đọc file cục bộ trên máy chủ sau SET disabled_filesystems = 'LocalFileSystem'
                with self.assertRaises(duckdb.Error):
                    conn.execute(f"SELECT * FROM read_parquet('{posix_local_path}')").fetchall()
                verified_assertions.append("local_filesystem_disabled")

                # 3. Không thể tạo SECRET mới hoặc bật lại autoinstall extension sau khi khóa
                with self.assertRaises(duckdb.Error):
                    conn.execute("SET autoinstall_known_extensions = true")
                verified_assertions.append("extensions_locked")

            executor = self._make_executor(_test_before_query_hook=_verify_after_lockdown)
            res = executor.execute(
                tables=self.tables,
                sql="SELECT COUNT(*) AS cnt FROM nhansu LIMIT 10",
                tenant_id="default",
            )
            self.assertEqual(res.rows, ((4,),))
            self.assertEqual(
                verified_assertions,
                ["settings_locked", "local_filesystem_disabled", "extensions_locked"],
            )

    def test_aggregations_group_by_join_truncation_and_cell_string_clipping(self) -> None:
        executor = self._make_executor()

        # 1. SUM, AVG, COUNT, GROUP BY & JOIN giữa 2 bảng
        join_sql = """
            SELECT
                n.phongban,
                p.truongphong,
                COUNT(*) AS so_nv,
                SUM(n.luong) AS tong_luong,
                AVG(n.luong) AS luong_tb
            FROM nhansu n
            JOIN phongban p ON n.phongban = p.tenphongban
            GROUP BY n.phongban, p.truongphong
            ORDER BY tong_luong DESC
        """
        res = executor.execute(tables=self.tables, sql=join_sql, tenant_id="default")
        self.assertEqual(res.columns, ("phongban", "truongphong", "so_nv", "tong_luong", "luong_tb"))
        self.assertEqual(len(res.rows), 3)
        self.assertEqual(res.rows[0], ("Kỹ thuật", "Minh Anh", 2, 50, 25.0))
        self.assertFalse(res.truncated)

        # 2. Phát hiện cờ truncated khi kết quả thực > max_rows và cắt chuỗi > 1000 ký tự
        res_trunc = executor.execute(
            tables=self.tables,
            sql="SELECT manv, motadai FROM nhansu ORDER BY manv",
            tenant_id="default",
            max_rows=2,
        )
        self.assertTrue(res_trunc.truncated)
        self.assertEqual(len(res_trunc.rows), 2)
        self.assertEqual(res_trunc.rows[0][0], "NV01")
        self.assertEqual(len(res_trunc.rows[0][1]), 1000)

    def test_cross_tenant_table_is_rejected_before_query(self) -> None:
        executor = self._make_executor()
        cross_table = AuthorizedSqlTable(
            view_name="nhansu",
            parquet_key="tenant_b/11111111-1111-4111-8111-111111111111/v1/tables/nhansu.parquet",
            tenant_id="tenant_b",
        )
        with self.assertRaises(SqlQueryExecutionError):
            executor.execute(
                tables=[cross_table],
                sql="SELECT * FROM nhansu LIMIT 1",
                tenant_id="default",
            )

    def test_unknown_column_error_returns_valid_columns_hint_without_leaking_secrets(self) -> None:
        executor = self._make_executor()
        with self.assertRaises(SqlQueryExecutionError) as ctx:
            executor.execute(
                tables=self.tables,
                sql="SELECT cot_khong_ton_tai FROM nhansu LIMIT 5",
                tenant_id="default",
            )
        msg = str(ctx.exception)
        self.assertIn("nhansu(manv, hoten, phongban, luong, motadai)", msg)
        self.assertNotIn("rag-test-s3-bucket", msg)
        self.assertNotIn("AKIA_READONLY_QUERY", msg)
        self.assertNotIn("SECRET_READONLY_QUERY_VALUE", msg)
        self.assertNotIn("s3://", msg)

    def test_watchdog_timer_interrupts_long_running_query_with_timeout_error(self) -> None:
        executor = self._make_executor(timeout_seconds=0.05)
        # Truy vấn cross-join tự nhân bản lớn để kích hoạt watchdog interrupt
        heavy_sql = """
            WITH RECURSIVE r(n) AS (
                SELECT 1
                UNION ALL
                SELECT n + 1 FROM r WHERE n < 200000
            )
            SELECT COUNT(*) FROM r a CROSS JOIN r b
        """
        with self.assertRaises(SqlQueryTimeoutError):
            executor.execute(
                tables=self.tables,
                sql=heavy_sql,
                tenant_id="default",
                timeout_seconds=0.05,
            )


if __name__ == "__main__":
    unittest.main()
