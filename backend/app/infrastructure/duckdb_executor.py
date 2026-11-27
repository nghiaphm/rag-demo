"""DuckDB in-memory SQL executor đọc Parquet từ S3 bằng credential chỉ đọc.

Tuân thủ nghiêm ngặt thứ tự khởi tạo và khóa cấu hình cho mỗi truy vấn:
1. Mở connection `:memory:` riêng biệt (đóng trong `finally`).
2. `LOAD httpfs` (cài sẵn trong image, không tự tải lúc runtime).
3. Tạo `SECRET` S3 chỉ đọc giới hạn `SCOPE 's3://{bucket}/{tenant_id}/'`.
4. `CREATE TEMP VIEW` cho từng bảng Parquet được cấp quyền.
5. `SET memory_limit`, `SET threads`, tắt spill đĩa (`temp_directory=''`, `max_temp_directory_size='0B'`).
6. `SET disabled_filesystems='LocalFileSystem'`.
7. `SET autoinstall_known_extensions=false`, `SET autoload_known_extensions=false`.
8. `SET lock_configuration=true`.
9. Thực thi SQL với watchdog `threading.Timer` gọi `conn.interrupt()`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import io
import re
import threading
from typing import Any
from urllib.parse import urlparse

import duckdb
import pyarrow.parquet as pq

from app.documents.ports import (
    AuthorizedSqlTable,
    SqlConfigurationError,
    SqlExecutionResult,
    SqlQueryExecutionError,
    SqlQueryExecutor,
    SqlQueryTimeoutError,
)
from app.shared.config import Settings, settings

_SAFE_TENANT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_VIEW_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")
_SAFE_MEMORY_LIMIT_RE = re.compile(r"^\d+(?:MB|GB|KB|MIB|GIB)$")
_MAX_CELL_STRING_CHARS = 1000


def _unwrap_secret(value: Any) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    raw = getter() if callable(getter) else str(value)
    stripped = raw.strip()
    return stripped or None


def _sql_quote_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _format_table_columns_hint(tables: Sequence[AuthorizedSqlTable]) -> str:
    if not tables:
        return ""
    parts: list[str] = []
    for tbl in tables:
        if tbl.columns:
            cols = ", ".join(tbl.columns)
            parts.append(f"{tbl.view_name}({cols})")
        else:
            parts.append(tbl.view_name)
    return f" Các bảng và cột hợp lệ: {'; '.join(parts)}."


def _truncate_cell_strings(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_CELL_STRING_CHARS:
        return value[:_MAX_CELL_STRING_CHARS]
    return value


class DuckDBSqlExecutor(SqlQueryExecutor):
    """Concrete DuckDB in-memory executor với S3 read-only secret và cấu hình bị khóa cứng."""

    def __init__(
        self,
        *,
        storage_backend: str,
        s3_bucket: str | None = None,
        s3_region: str = "us-east-1",
        s3_endpoint_url: str | None = None,
        query_access_key_id: str | None = None,
        query_secret_access_key: str | None = None,
        ingest_access_key_id: str | None = None,
        local_parquet_loader: Callable[[str], bytes] | None = None,
        memory_limit: str = "512MB",
        threads: int = 2,
        timeout_seconds: float = 15.0,
        max_rows: int = 200,
        _test_parquet_bytes_by_key: Mapping[str, bytes] | None = None,
        _test_before_query_hook: Callable[[duckdb.DuckDBPyConnection], None] | None = None,
    ) -> None:
        normalized_backend = (storage_backend or "").strip().lower()
        if normalized_backend not in ("local", "s3"):
            raise SqlConfigurationError(
                "Tool run_sql chỉ hỗ trợ STORAGE_BACKEND là 'local' hoặc 's3'."
            )

        normalized_bucket = (s3_bucket or "").strip()
        q_key = (query_access_key_id or "").strip()
        q_secret = (query_secret_access_key or "").strip()
        i_key = (ingest_access_key_id or "").strip()

        if normalized_backend == "s3":
            if not normalized_bucket:
                raise SqlConfigurationError("Thiếu cấu hình S3_BUCKET cho DuckDB SQL executor.")
            if not q_key or not q_secret:
                raise SqlConfigurationError(
                    "Thiếu credential chỉ đọc S3_QUERY_ACCESS_KEY_ID / S3_QUERY_SECRET_ACCESS_KEY."
                )
            if i_key and q_key == i_key:
                raise SqlConfigurationError(
                    "Credential S3_QUERY_ACCESS_KEY_ID bắt buộc phải khác S3_INGEST_ACCESS_KEY_ID."
                )
        elif local_parquet_loader is None and _test_parquet_bytes_by_key is None:
            raise SqlConfigurationError(
                "Thiếu local_parquet_loader cho DuckDB SQL executor ở chế độ STORAGE_BACKEND='local'."
            )

        normalized_mem = (memory_limit or "512MB").strip().upper()
        if not _SAFE_MEMORY_LIMIT_RE.fullmatch(normalized_mem):
            raise SqlConfigurationError("DUCKDB_MEMORY_LIMIT không hợp lệ.")
        if type(threads) is not int or not (1 <= threads <= 32):
            raise SqlConfigurationError("DUCKDB_THREADS phải là số nguyên từ 1 đến 32.")
        if timeout_seconds <= 0:
            raise SqlConfigurationError("DUCKDB_QUERY_TIMEOUT_SECONDS phải lớn hơn 0.")
        if type(max_rows) is not int or max_rows < 1:
            raise SqlConfigurationError("DUCKDB_MAX_ROWS phải >= 1.")

        self._storage_backend = normalized_backend
        self._bucket = normalized_bucket
        self._region = (s3_region or "us-east-1").strip() or "us-east-1"
        self._endpoint_url = s3_endpoint_url.strip() if s3_endpoint_url else None
        self._query_access_key_id = q_key
        self._query_secret_access_key = q_secret
        self._local_parquet_loader = local_parquet_loader
        self._memory_limit = normalized_mem
        self._threads = threads
        self._timeout_seconds = float(timeout_seconds)
        self._max_rows = int(max_rows)
        self._test_parquet_bytes_by_key = _test_parquet_bytes_by_key
        self._test_before_query_hook = _test_before_query_hook

    def _configure_s3_secret(
        self,
        conn: duckdb.DuckDBPyConnection,
        tenant_id: str,
    ) -> None:
        scope_prefix = f"s3://{self._bucket}/{tenant_id}/"
        secret_parts = [
            "TYPE S3",
            f"KEY_ID {_sql_quote_literal(self._query_access_key_id)}",
            f"SECRET {_sql_quote_literal(self._query_secret_access_key)}",
            f"REGION {_sql_quote_literal(self._region)}",
            f"SCOPE {_sql_quote_literal(scope_prefix)}",
        ]
        if self._endpoint_url:
            parsed = urlparse(self._endpoint_url)
            host_port = parsed.netloc or parsed.path
            use_ssl = "true" if parsed.scheme == "https" else "false"
            secret_parts.append(f"ENDPOINT {_sql_quote_literal(host_port)}")
            secret_parts.append(f"USE_SSL {use_ssl}")
            secret_parts.append("URL_STYLE 'path'")

        secret_sql = f"CREATE SECRET s3_readonly_query ({', '.join(secret_parts)})"
        conn.execute(secret_sql)

    def _create_authorized_views(
        self,
        conn: duckdb.DuckDBPyConnection,
        tables: Sequence[AuthorizedSqlTable],
        tenant_id: str,
    ) -> None:
        expected_prefix = f"{tenant_id}/"
        for idx, tbl in enumerate(tables):
            if not _SAFE_VIEW_RE.fullmatch(tbl.view_name):
                raise SqlQueryExecutionError("Tên view bảng không hợp lệ.")
            if tbl.tenant_id != tenant_id or not tbl.parquet_key.startswith(expected_prefix):
                raise SqlQueryExecutionError(
                    "Bảng dữ liệu không thuộc phạm vi tenant hiện tại."
                )
            if "\\" in tbl.parquet_key or ".." in tbl.parquet_key.split("/"):
                raise SqlQueryExecutionError("Đường dẫn Parquet không hợp lệ.")

            if self._test_parquet_bytes_by_key is not None:
                raw_parquet = self._test_parquet_bytes_by_key.get(tbl.parquet_key)
                if raw_parquet is None:
                    raise SqlQueryExecutionError("Không tìm thấy dữ liệu bảng Parquet để truy vấn.")
                arrow_table = pq.read_table(io.BytesIO(raw_parquet))
                internal_rel = f"__inmem_parquet_{idx}"
                conn.register(internal_rel, arrow_table)
                conn.execute(
                    f'CREATE TEMP VIEW "{tbl.view_name}" AS SELECT * FROM "{internal_rel}"'
                )
            elif self._storage_backend == "local":
                if self._local_parquet_loader is None:
                    raise SqlConfigurationError(
                        "Thiếu local_parquet_loader khi thực thi SQL ở chế độ local."
                    )
                try:
                    raw_parquet = self._local_parquet_loader(tbl.parquet_key)
                except Exception:
                    raise SqlQueryExecutionError(
                        "Không tìm thấy hoặc không thể đọc dữ liệu bảng Parquet để truy vấn."
                    ) from None
                arrow_table = pq.read_table(io.BytesIO(raw_parquet))
                internal_rel = f"__inmem_parquet_{idx}"
                conn.register(internal_rel, arrow_table)
                conn.execute(
                    f'CREATE TEMP VIEW "{tbl.view_name}" AS SELECT * FROM "{internal_rel}"'
                )
            else:
                s3_uri = f"s3://{self._bucket}/{tbl.parquet_key}"
                conn.execute(
                    f'CREATE TEMP VIEW "{tbl.view_name}" AS '
                    f"SELECT * FROM read_parquet({_sql_quote_literal(s3_uri)})"
                )

    def _apply_security_lockdown(self, conn: duckdb.DuckDBPyConnection) -> None:
        conn.execute(f"SET memory_limit = {_sql_quote_literal(self._memory_limit)}")
        conn.execute(f"SET threads = {int(self._threads)}")
        conn.execute("SET temp_directory = ''")
        conn.execute("SET max_temp_directory_size = '0B'")
        conn.execute("SET disabled_filesystems = 'LocalFileSystem'")
        conn.execute("SET autoinstall_known_extensions = false")
        conn.execute("SET autoload_known_extensions = false")
        conn.execute("SET lock_configuration = true")

    def _map_duckdb_error(
        self,
        exc: Exception,
        *,
        timed_out: bool,
        tables: Sequence[AuthorizedSqlTable],
    ) -> SqlQueryTimeoutError | SqlQueryExecutionError:
        raw_message = str(exc) or ""
        lowered = raw_message.lower()
        if timed_out or isinstance(exc, duckdb.InterruptException) or "interrupt" in lowered:
            return SqlQueryTimeoutError("Truy vấn SQL vượt quá thời gian cho phép.")

        if isinstance(exc, (duckdb.BinderException, duckdb.CatalogException)) or (
            "column" in lowered
            or "referenced" in lowered
            or "not found" in lowered
            or "does not have a column" in lowered
        ):
            hint = _format_table_columns_hint(tables)
            return SqlQueryExecutionError(
                f"Tên cột hoặc bảng trong câu lệnh SQL không khớp với lược đồ.{hint}"
            )

        if isinstance(exc, duckdb.ParserException):
            return SqlQueryExecutionError("Cú pháp câu lệnh SQL không hợp lệ với DuckDB.")

        if "disabled" in lowered or "configuration is locked" in lowered or "permission" in lowered:
            return SqlQueryExecutionError(
                "Thao tác SQL bị chặn bởi chính sách bảo mật sandbox của DuckDB."
            )

        return SqlQueryExecutionError(
            "Không thể thực thi câu lệnh SQL trên dữ liệu bảng."
        )

    def execute(
        self,
        *,
        tables: Sequence[AuthorizedSqlTable],
        sql: str,
        tenant_id: str,
        max_rows: int | None = None,
        timeout_seconds: float | None = None,
    ) -> SqlExecutionResult:
        normalized_tenant = (tenant_id or "").strip()
        if not _SAFE_TENANT_RE.fullmatch(normalized_tenant):
            raise SqlQueryExecutionError("tenant_id không hợp lệ.")
        if not isinstance(sql, str) or not sql.strip():
            raise SqlQueryExecutionError("Câu lệnh SQL không được rỗng.")

        effective_max_rows = (
            int(max_rows) if max_rows is not None and max_rows >= 1 else self._max_rows
        )
        effective_timeout = (
            float(timeout_seconds)
            if timeout_seconds is not None and timeout_seconds > 0
            else self._timeout_seconds
        )

        conn = duckdb.connect(":memory:")
        timed_out = False
        timer: threading.Timer | None = None

        def _interrupt_on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            try:
                conn.interrupt()
            except Exception:
                pass

        try:
            # 1. LOAD httpfs & tạo SECRET S3 chỉ đọc với SCOPE theo tenant (khi chạy S3 thật)
            if self._storage_backend == "s3" and self._test_parquet_bytes_by_key is None:
                try:
                    conn.execute("LOAD httpfs")
                except Exception:
                    raise SqlConfigurationError(
                        "Extension httpfs của DuckDB chưa được cài đặt sẵn trong môi trường."
                    ) from None
                self._configure_s3_secret(conn, normalized_tenant)

            # 2. CREATE TEMP VIEW cho từng bảng được cấp quyền
            self._create_authorized_views(conn, tables, normalized_tenant)

            # 3. SET memory_limit/threads -> tắt spill đĩa -> tắt LocalFileSystem -> tắt autoinstall/autoload -> khóa cấu hình
            self._apply_security_lockdown(conn)

            if self._test_before_query_hook is not None:
                self._test_before_query_hook(conn)

            # 4. Chạy SQL với watchdog timer và lấy tối đa max_rows + 1 hàng để phát hiện truncated
            timer = threading.Timer(effective_timeout, _interrupt_on_timeout)
            timer.daemon = True
            timer.start()

            cursor = conn.execute(sql)
            description = cursor.description or ()
            columns = tuple(str(col[0]) for col in description)
            fetched = cursor.fetchmany(effective_max_rows + 1)
            if timed_out:
                raise SqlQueryTimeoutError("Truy vấn SQL vượt quá thời gian cho phép.")

            truncated = len(fetched) > effective_max_rows
            bounded_rows = tuple(
                tuple(_truncate_cell_strings(cell) for cell in row)
                for row in fetched[:effective_max_rows]
            )
            return SqlExecutionResult(
                columns=columns,
                rows=bounded_rows,
                truncated=truncated,
            )
        except (SqlConfigurationError, SqlQueryTimeoutError, SqlQueryExecutionError):
            raise
        except Exception as exc:
            raise self._map_duckdb_error(
                exc,
                timed_out=timed_out,
                tables=tables,
            ) from None
        finally:
            if timer is not None:
                timer.cancel()
            try:
                conn.close()
            except Exception:
                pass


def create_duckdb_sql_executor(config: Settings | Any = settings) -> DuckDBSqlExecutor:
    """Factory chính thức khởi tạo DuckDBSqlExecutor từ Settings cho cả Local và S3 (luôn khóa đĩa cục bộ trong DuckDB)."""
    backend = str(getattr(config, "storage_backend", "local") or "local").strip().lower()
    local_loader: Callable[[str], bytes] | None = None
    if backend == "local":
        from app.infrastructure.storage import create_file_storage

        local_loader = create_file_storage(config, backend="local").get
    return DuckDBSqlExecutor(
        storage_backend=backend,
        s3_bucket=getattr(config, "s3_bucket", None),
        s3_region=str(getattr(config, "s3_region", "us-east-1") or "us-east-1"),
        s3_endpoint_url=getattr(config, "s3_endpoint_url", None),
        query_access_key_id=_unwrap_secret(getattr(config, "s3_query_access_key_id", None)),
        query_secret_access_key=_unwrap_secret(
            getattr(config, "s3_query_secret_access_key", None)
        ),
        ingest_access_key_id=_unwrap_secret(
            getattr(config, "s3_ingest_access_key_id", None)
        ),
        local_parquet_loader=local_loader,
        memory_limit=str(getattr(config, "duckdb_memory_limit", "512MB") or "512MB"),
        threads=int(getattr(config, "duckdb_threads", 2)),
        timeout_seconds=float(getattr(config, "duckdb_query_timeout_seconds", 15.0)),
        max_rows=int(getattr(config, "duckdb_max_rows", 200)),
    )
