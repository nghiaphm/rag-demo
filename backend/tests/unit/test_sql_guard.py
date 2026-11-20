"""Unit & security tests cho Giai đoạn 3 (T3.2 & T3.5): sql_guard.py."""

from __future__ import annotations

import unittest

from app.documents.excel.sql_guard import validate_and_rewrite_sql


class SqlGuardSecurityTests(unittest.TestCase):
    ALLOWED = ("nhansu", "phong_ban")

    def assert_rejected(self, sql: str) -> str:
        result = validate_and_rewrite_sql(sql, self.ALLOWED, max_rows=200)
        self.assertFalse(result.ok, f"Expected SQL to be rejected, but got ok=True: {sql} -> {result.normalized_sql}")
        self.assertIsNone(result.normalized_sql)
        self.assertTrue(result.reason, "Rejection reason must not be empty")
        return result.reason or ""

    def test_blocks_multi_statement_payloads(self) -> None:
        self.assert_rejected("SELECT * FROM nhansu; DROP TABLE nhansu")
        self.assert_rejected("SELECT 1 FROM nhansu; SELECT 2 FROM nhansu")

    def test_blocks_ddl_statements(self) -> None:
        self.assert_rejected("CREATE TABLE hacked AS SELECT * FROM nhansu")
        self.assert_rejected("DROP TABLE nhansu")
        self.assert_rejected("ALTER TABLE nhansu ADD COLUMN x INT")

    def test_blocks_dml_statements(self) -> None:
        self.assert_rejected("INSERT INTO nhansu VALUES ('NV99', 'Hacker')")
        self.assert_rejected("UPDATE nhansu SET base_salary_million = 999")
        self.assert_rejected("DELETE FROM nhansu")

    def test_blocks_pragma_and_set_commands(self) -> None:
        self.assert_rejected("PRAGMA show_tables")
        self.assert_rejected("PRAGMA database_list")
        self.assert_rejected("SET memory_limit = '10GB'")
        self.assert_rejected("SET disabled_filesystems = ''")
        self.assert_rejected("SET lock_configuration = false")

    def test_blocks_copy_attach_install_load_call_export_and_select_into(self) -> None:
        self.assert_rejected("COPY nhansu TO '/tmp/leak.parquet'")
        self.assert_rejected("COPY nhansu FROM '/etc/passwd'")
        self.assert_rejected("ATTACH '/etc/passwd' AS ext_db")
        self.assert_rejected("DETACH ext_db")
        self.assert_rejected("INSTALL httpfs")
        self.assert_rejected("LOAD httpfs")
        self.assert_rejected("CALL pragma_version()")
        self.assert_rejected("EXPORT DATABASE '/tmp/dump'")
        self.assert_rejected("SELECT * INTO leaked_table FROM nhansu")

    def test_blocks_direct_file_reader_table_functions_and_string_paths(self) -> None:
        self.assert_rejected("SELECT * FROM read_parquet('/etc/passwd')")
        self.assert_rejected("SELECT * FROM read_parquet('s3://other-bucket/secret.parquet')")
        self.assert_rejected("SELECT * FROM read_csv('/etc/passwd')")
        self.assert_rejected("SELECT * FROM read_csv_auto('/etc/passwd')")
        self.assert_rejected("SELECT * FROM read_json('/etc/passwd')")
        self.assert_rejected("SELECT * FROM glob('/etc/*')")
        self.assert_rejected("SELECT * FROM 'file.parquet'")
        self.assert_rejected("SELECT * FROM 's3://bucket/default/doc/v1/tables/nhansu.parquet'")
        self.assert_rejected("SELECT * FROM parquet_scan('file.parquet')")

    def test_blocks_other_table_valued_functions_in_from_and_join(self) -> None:
        self.assert_rejected("SELECT * FROM generate_series(1, 100)")
        self.assert_rejected("SELECT * FROM range(100)")
        self.assert_rejected("SELECT * FROM unnest([1, 2, 3])")
        self.assert_rejected("SELECT * FROM query_table('nhansu')")
        self.assert_rejected("SELECT * FROM nhansu JOIN read_parquet('x.parquet') ON 1=1")

    def test_blocks_duckdb_system_and_environment_functions(self) -> None:
        self.assert_rejected("SELECT * FROM duckdb_secrets()")
        self.assert_rejected("SELECT * FROM duckdb_settings()")
        self.assert_rejected("SELECT * FROM duckdb_extensions()")
        self.assert_rejected("SELECT getenv('AWS_SECRET_ACCESS_KEY') FROM nhansu")
        self.assert_rejected("SELECT current_setting('memory_limit') FROM nhansu")
        self.assert_rejected("SELECT read_text('/etc/passwd') FROM nhansu")
        self.assert_rejected("SELECT read_blob('/etc/passwd') FROM nhansu")

    def test_blocks_unwhitelisted_tables_qualified_schemas_subqueries_and_cte_shadowing(self) -> None:
        reason = self.assert_rejected("SELECT * FROM bang_luong_bi_mat")
        self.assertIn("nhansu", reason)
        self.assertIn("phong_ban", reason)

        self.assert_rejected("SELECT * FROM main.nhansu")
        self.assert_rejected("SELECT * FROM memory.main.nhansu")
        self.assert_rejected("SELECT * FROM (SELECT * FROM secret_table) AS sub")
        self.assert_rejected("WITH c AS (SELECT * FROM secret_table) SELECT * FROM c")
        # CTE trùng tên bảng được cấp quyền nhằm che giấu bảng thật
        self.assert_rejected("WITH nhansu AS (SELECT 1 AS x) SELECT * FROM nhansu")
        # CTE chỉ chọn hằng số không tham chiếu bảng thật
        self.assert_rejected("WITH c AS (SELECT 1 AS x) SELECT * FROM c")

    def test_blocks_obfuscated_comments_mixed_case_and_whitespace_bypasses(self) -> None:
        self.assert_rejected("/* comment */ SeLeCt * FrOm /* bypass */ ReAd_PaRqUeT('/etc/passwd')")
        self.assert_rejected("SELECT\n\t/* hidden */ *\nFROM\n\tduckdb_secrets()")
        self.assert_rejected("SeLeCt\t*\nFrOm\tnhansu;\n/*x*/DrOp\tTaBlE\tnhansu")

    def test_rewrites_ast_to_enforce_max_rows_on_select_and_union(self) -> None:
        # 1. Chưa có LIMIT -> tự thêm LIMIT max_rows
        res1 = validate_and_rewrite_sql(
            "SeLeCt /* cmt */ department, COUNT(*) AS cnt FROM NhanSu GROUP BY department",
            self.ALLOWED,
            max_rows=200,
        )
        self.assertTrue(res1.ok)
        self.assertEqual(res1.referenced_tables, ("nhansu",))
        self.assertIn("LIMIT 200", res1.normalized_sql or "")
        self.assertNotIn("/* cmt */", res1.normalized_sql or "")

        # 2. Có LIMIT lớn hơn max_rows -> hạ xuống max_rows
        res2 = validate_and_rewrite_sql(
            "SELECT * FROM nhansu LIMIT 50000",
            self.ALLOWED,
            max_rows=200,
        )
        self.assertTrue(res2.ok)
        self.assertIn("LIMIT 200", res2.normalized_sql or "")
        self.assertNotIn("50000", res2.normalized_sql or "")

        # 3. Có LIMIT nhỏ hơn max_rows -> giữ nguyên LIMIT nhỏ
        res3 = validate_and_rewrite_sql(
            "SELECT * FROM nhansu LIMIT 5",
            self.ALLOWED,
            max_rows=200,
        )
        self.assertTrue(res3.ok)
        self.assertIn("LIMIT 5", res3.normalized_sql or "")

        # 4. UNION không có LIMIT -> bọc SELECT * FROM (...) LIMIT max_rows
        res4 = validate_and_rewrite_sql(
            "SELECT department FROM nhansu UNION SELECT ten_phong_ban FROM phong_ban",
            self.ALLOWED,
            max_rows=100,
        )
        self.assertTrue(res4.ok)
        self.assertEqual(res4.referenced_tables, ("nhansu", "phong_ban"))
        self.assertTrue((res4.normalized_sql or "").startswith("SELECT * FROM ("))
        self.assertTrue((res4.normalized_sql or "").endswith("LIMIT 100"))

        # 5. CTE hợp lệ + JOIN giữa 2 bảng trong whitelist
        res5 = validate_and_rewrite_sql(
            """
            WITH active_emp AS (
                SELECT department, base_salary_million
                FROM nhansu
                WHERE status = 'Chính thức'
            )
            SELECT a.department, AVG(a.base_salary_million) AS avg_sal, p.ngan_sach
            FROM active_emp a
            JOIN phong_ban p ON a.department = p.ten_phong_ban
            GROUP BY a.department, p.ngan_sach
            """,
            self.ALLOWED,
            max_rows=200,
        )
        self.assertTrue(res5.ok)
        self.assertEqual(res5.referenced_tables, ("nhansu", "phong_ban"))
        self.assertIn("LIMIT 200", res5.normalized_sql or "")


if __name__ == "__main__":
    unittest.main()
