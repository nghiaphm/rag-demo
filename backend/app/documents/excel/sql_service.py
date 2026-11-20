"""Service phân quyền Table Catalog, kiểm duyệt SQL và thực thi `run_sql` trên DuckDB.

Module này nằm trong `app.documents.excel`, tuân thủ ranh giới Hexagonal Architecture:
- Không import `app.infrastructure`, `app.chat`, hay `app.api`.
- Nhận `SqlQueryExecutor` qua port `app.documents.ports.SqlQueryExecutor`.
- Nhận `(user, tenant_id, session_scope)` từ Backend; LLM chỉ được truyền chuỗi `sql`.
- Ghi structured audit log cho MỖI truy vấn (`OK` / `GUARD_REJECTED` / `TIMEOUT` / `ERROR`),
  tuyệt đối không log dữ liệu hàng trả về hay credential.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
import json
import logging
import math
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from app.documents.excel.sql_guard import validate_and_rewrite_sql
from app.documents.models import (
    DocumentRecord,
    DocumentStatus,
    DocumentTableCatalogRecord,
    TableColumnSchema,
)
from app.documents.ports import (
    AuthorizedSqlTable,
    SqlConfigurationError,
    SqlEngineError,
    SqlQueryExecutionError,
    SqlQueryExecutor,
    SqlQueryTimeoutError,
)
from app.shared.auth import UserContext, can_access_resource
from app.shared.config import settings
from app.tool_use.contracts import (
    RunSqlArguments,
    ToolContractError,
    ToolDefinition,
    ToolEnvelope,
    ToolHandler,
    failure_result,
    success_result,
    validate_arguments,
)

logger = logging.getLogger(__name__)

AuditOutcome = Literal["OK", "GUARD_REJECTED", "TIMEOUT", "ERROR"]
_MAX_AUDIT_SQL_CHARS = 2000
_MAX_CELL_STR_CHARS = 1000


@dataclass(frozen=True, slots=True)
class AuthorizedTableBinding:
    """Ánh xạ giữa alias view SQL với tài liệu, sheet và schema cột gốc."""

    view_name: str
    tenant_id: str
    document_id: str
    version_id: str
    file_name: str
    sheet_name: str
    table_name: str
    parquet_key: str
    row_count: int
    columns: tuple[TableColumnSchema, ...]
    sample_rows: tuple[dict[str, Any], ...]
    has_formula_values: bool = False

    def to_authorized_sql_table(self) -> AuthorizedSqlTable:
        return AuthorizedSqlTable(
            view_name=self.view_name,
            parquet_key=self.parquet_key,
            tenant_id=self.tenant_id,
            document_id=self.document_id,
            version_id=self.version_id,
            file_name=self.file_name,
            sheet_name=self.sheet_name,
            columns=tuple(col.name for col in self.columns),
        )

    def to_catalog_metadata(self) -> dict[str, Any]:
        return {
            "view_name": self.view_name,
            "document_id": self.document_id,
            "version_id": self.version_id,
            "file_name": self.file_name,
            "sheet_name": self.sheet_name,
            "table_name": self.table_name,
            "row_count": self.row_count,
            "columns": [
                {
                    "name": col.name,
                    "original_name": col.original_name,
                    "type": col.type,
                    "nullable": col.nullable,
                    "description": col.description,
                }
                for col in self.columns
            ],
        }


def _to_json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        if value == value.to_integral_value():
            int_val = int(value)
            if -(1 << 63) <= int_val <= (1 << 63) - 1:
                return int_val
        as_float = float(value)
        return as_float if math.isfinite(as_float) else str(value)[:_MAX_CELL_STR_CHARS]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")[:_MAX_CELL_STR_CHARS]
    if isinstance(value, str):
        return value[:_MAX_CELL_STR_CHARS]
    if isinstance(value, (list, tuple)):
        return [_to_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _to_json_safe_value(v) for k, v in value.items()}
    return str(value)[:_MAX_CELL_STR_CHARS]


def _is_document_in_session_scope(document_id: str, session_scope: Any) -> bool:
    if session_scope is None:
        return True
    raw_mode = getattr(session_scope, "mode", None)
    mode_val = getattr(raw_mode, "value", raw_mode)
    mode_str = str(mode_val or "ALL_ACTIVE").strip().upper()
    if mode_str == "SELECTED_DOCUMENTS":
        allowed_ids = {str(doc_id) for doc_id in (getattr(session_scope, "document_ids", ()) or ())}
        return document_id in allowed_ids
    return True


def _allocate_deterministic_view_aliases(
    items: list[tuple[DocumentRecord, DocumentTableCatalogRecord]],
) -> list[AuthorizedTableBinding]:
    """Gán alias view ổn định: dùng `table_name` nếu duy nhất, nếu trùng giữa nhiều file thì gắn hậu tố cố định theo document_id."""
    sorted_items = sorted(
        items,
        key=lambda pair: (pair[0].document_id, pair[1].table_name, pair[1].version_id),
    )
    name_counts = Counter(pair[1].table_name for pair in sorted_items)
    used_aliases: set[str] = set()
    bindings: list[AuthorizedTableBinding] = []

    for doc, cat in sorted_items:
        base_name = cat.table_name
        if name_counts[base_name] == 1 and base_name not in used_aliases:
            alias = base_name
        else:
            doc_token = doc.document_id.replace("-", "").lower()[:8]
            max_base = 63 - len(doc_token) - 1
            candidate = f"{base_name[:max_base].rstrip('_')}_{doc_token}"
            alias = candidate
            counter = 2
            while alias in used_aliases:
                suffix = f"_{doc_token}_{counter}"
                alias = f"{base_name[: 63 - len(suffix)].rstrip('_')}{suffix}"
                counter += 1

        used_aliases.add(alias)
        bindings.append(
            AuthorizedTableBinding(
                view_name=alias,
                tenant_id=cat.tenant_id,
                document_id=doc.document_id,
                version_id=cat.version_id,
                file_name=doc.file_name,
                sheet_name=cat.sheet_name,
                table_name=cat.table_name,
                parquet_key=cat.parquet_key,
                row_count=cat.row_count,
                columns=tuple(cat.columns),
                sample_rows=tuple(cat.sample_rows),
                has_formula_values=cat.has_formula_values,
            )
        )

    return bindings


class ExcelSqlService:
    """Service điều phối kiểm tra RBAC/scope trên Table Catalog, sql_guard và DuckDBSqlExecutor."""

    def __init__(
        self,
        *,
        repository: Any,
        executor: SqlQueryExecutor | None,
        max_rows: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.repository = repository
        self.executor = executor
        self.max_rows = (
            int(max_rows)
            if max_rows is not None and max_rows >= 1
            else int(getattr(settings, "duckdb_max_rows", 200))
        )
        self.timeout_seconds = (
            float(timeout_seconds)
            if timeout_seconds is not None and timeout_seconds > 0
            else float(getattr(settings, "duckdb_query_timeout_seconds", 15.0))
        )

    def resolve_effective_tenant_id(
        self,
        user: UserContext | None,
        tenant_id: str | None = None,
    ) -> str:
        if tenant_id and tenant_id.strip():
            return tenant_id.strip()
        if user is not None and getattr(user, "tenant_id", None):
            return user.tenant_id.strip()
        return settings.default_tenant_id

    def list_authorized_tables(
        self,
        *,
        user: UserContext | None = None,
        tenant_id: str | None = None,
        session_scope: Any = None,
    ) -> list[AuthorizedTableBinding]:
        """Lọc danh sách bảng Parquet thuộc active_version_id của các tài liệu .xlsx INDEXED mà user được phép đọc."""
        effective_tenant_id = self.resolve_effective_tenant_id(user, tenant_id)
        documents: list[DocumentRecord] = self.repository.list_documents(
            include_deleted=False,
            offset=0,
            limit=500,
        )

        authorized_docs_by_active_version: dict[str, DocumentRecord] = {}
        for doc in documents:
            if doc.status != DocumentStatus.INDEXED or doc.deleted_at is not None:
                continue
            if not doc.active_version_id:
                continue
            if Path(doc.file_name).suffix.lower() != ".xlsx":
                continue
            doc_tenant = (getattr(doc, "tenant_id", None) or "default").strip()
            if doc_tenant != effective_tenant_id:
                continue
            if not can_access_resource(
                user=user,
                owner_id=doc.owner_id,
                allowed_roles=doc.allowed_roles,
            ):
                continue
            if not _is_document_in_session_scope(doc.document_id, session_scope):
                continue
            authorized_docs_by_active_version[doc.active_version_id] = doc

        if not authorized_docs_by_active_version:
            return []

        list_tables_fn = getattr(self.repository, "list_tables_for_versions", None)
        if not callable(list_tables_fn):
            return []

        active_version_ids = sorted(authorized_docs_by_active_version.keys())
        catalog_records: list[DocumentTableCatalogRecord] = list_tables_fn(
            active_version_ids,
            tenant_id=effective_tenant_id,
        )

        valid_pairs: list[tuple[DocumentRecord, DocumentTableCatalogRecord]] = []
        for record in catalog_records:
            doc = authorized_docs_by_active_version.get(record.version_id)
            if doc is None or doc.document_id != record.document_id:
                continue
            if record.tenant_id != effective_tenant_id:
                continue
            if not record.parquet_key or not record.parquet_key.endswith(".parquet"):
                continue
            valid_pairs.append((doc, record))

        return _allocate_deterministic_view_aliases(valid_pairs)

    def _emit_audit_log(
        self,
        *,
        user: UserContext | None,
        tenant_id: str,
        referenced_bindings: Sequence[AuthorizedTableBinding],
        sql: str,
        duration_ms: float,
        row_count: int,
        outcome: AuditOutcome,
    ) -> None:
        audit_payload = {
            "event": "excel_sql_query_audit",
            "user_id": user.user_id if user is not None else "anonymous",
            "tenant_id": tenant_id,
            "referenced_documents": [
                {
                    "document_id": item.document_id,
                    "version_id": item.version_id,
                    "view_name": item.view_name,
                    "table_name": item.table_name,
                }
                for item in referenced_bindings
            ],
            "sql": (sql or "")[:_MAX_AUDIT_SQL_CHARS],
            "duration_ms": round(duration_ms, 2),
            "row_count": int(row_count),
            "outcome": outcome,
        }
        logger.info("excel_sql_audit %s", json.dumps(audit_payload, ensure_ascii=False, sort_keys=True))

    def execute_query(
        self,
        *,
        sql: str,
        user: UserContext | None = None,
        tenant_id: str | None = None,
        session_scope: Any = None,
    ) -> ToolEnvelope:
        """Thực thi luồng run_sql đầy đủ: RBAC catalog -> sql_guard -> DuckDBSqlExecutor -> ToolEnvelope."""
        start_time = monotonic()
        effective_tenant_id = self.resolve_effective_tenant_id(user, tenant_id)

        try:
            bindings = self.list_authorized_tables(
                user=user,
                tenant_id=effective_tenant_id,
                session_scope=session_scope,
            )
        except Exception:
            duration_ms = (monotonic() - start_time) * 1000.0
            self._emit_audit_log(
                user=user,
                tenant_id=effective_tenant_id,
                referenced_bindings=(),
                sql=sql,
                duration_ms=duration_ms,
                row_count=0,
                outcome="ERROR",
            )
            return failure_result("run_sql", "TOOL_QUERY_FAILED")

        if not bindings:
            duration_ms = (monotonic() - start_time) * 1000.0
            self._emit_audit_log(
                user=user,
                tenant_id=effective_tenant_id,
                referenced_bindings=(),
                sql=sql,
                duration_ms=duration_ms,
                row_count=0,
                outcome="OK",
            )
            return success_result(
                "run_sql",
                {
                    "status": "NO_TABLES_AVAILABLE",
                    "message": "Hiện không có bảng dữ liệu Excel (.xlsx) nào khả dụng trong phạm vi truy cập.",
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "truncated": False,
                    "referenced_tables": [],
                },
            )

        bindings_by_view = {b.view_name: b for b in bindings}
        # Cho phép AST limit là max_rows + 1 để executor lấy max_rows + 1 hàng và bật cờ truncated chính xác
        guard_result = validate_and_rewrite_sql(
            sql,
            bindings_by_view.keys(),
            max_rows=self.max_rows + 1,
        )
        if not guard_result.ok or not guard_result.normalized_sql:
            duration_ms = (monotonic() - start_time) * 1000.0
            self._emit_audit_log(
                user=user,
                tenant_id=effective_tenant_id,
                referenced_bindings=(),
                sql=sql,
                duration_ms=duration_ms,
                row_count=0,
                outcome="GUARD_REJECTED",
            )
            return {
                "ok": False,
                "tool": "run_sql",
                "data": None,
                "error": {
                    "code": "TOOL_INVALID_ARGUMENTS",
                    "message": guard_result.reason or "Câu lệnh SQL không hợp lệ.",
                    "retryable": False,
                },
            }

        referenced_bindings = [
            bindings_by_view[view_name]
            for view_name in guard_result.referenced_tables
            if view_name in bindings_by_view
        ]

        if self.executor is None:
            duration_ms = (monotonic() - start_time) * 1000.0
            self._emit_audit_log(
                user=user,
                tenant_id=effective_tenant_id,
                referenced_bindings=referenced_bindings,
                sql=guard_result.normalized_sql,
                duration_ms=duration_ms,
                row_count=0,
                outcome="ERROR",
            )
            return {
                "ok": False,
                "tool": "run_sql",
                "data": None,
                "error": {
                    "code": "TOOL_QUERY_FAILED",
                    "message": "DuckDB SQL executor chưa sẵn sàng (yêu cầu STORAGE_BACKEND='s3' và S3_QUERY_* hợp lệ).",
                    "retryable": False,
                },
            }

        try:
            exec_result = self.executor.execute(
                tables=[b.to_authorized_sql_table() for b in referenced_bindings],
                sql=guard_result.normalized_sql,
                tenant_id=effective_tenant_id,
                max_rows=self.max_rows,
                timeout_seconds=self.timeout_seconds,
            )
        except SqlQueryTimeoutError:
            duration_ms = (monotonic() - start_time) * 1000.0
            self._emit_audit_log(
                user=user,
                tenant_id=effective_tenant_id,
                referenced_bindings=referenced_bindings,
                sql=guard_result.normalized_sql,
                duration_ms=duration_ms,
                row_count=0,
                outcome="TIMEOUT",
            )
            return failure_result("run_sql", "TOOL_TIMEOUT")
        except SqlQueryExecutionError as exc:
            duration_ms = (monotonic() - start_time) * 1000.0
            self._emit_audit_log(
                user=user,
                tenant_id=effective_tenant_id,
                referenced_bindings=referenced_bindings,
                sql=guard_result.normalized_sql,
                duration_ms=duration_ms,
                row_count=0,
                outcome="ERROR",
            )
            return {
                "ok": False,
                "tool": "run_sql",
                "data": None,
                "error": {
                    "code": "TOOL_INVALID_ARGUMENTS",
                    "message": str(exc) or "Không thể thực thi câu lệnh SQL.",
                    "retryable": False,
                },
            }
        except (SqlConfigurationError, SqlEngineError, Exception):
            duration_ms = (monotonic() - start_time) * 1000.0
            self._emit_audit_log(
                user=user,
                tenant_id=effective_tenant_id,
                referenced_bindings=referenced_bindings,
                sql=guard_result.normalized_sql,
                duration_ms=duration_ms,
                row_count=0,
                outcome="ERROR",
            )
            return failure_result("run_sql", "TOOL_QUERY_FAILED")

        safe_columns = [str(c) for c in exec_result.columns]
        safe_rows = [
            {
                col_name: _to_json_safe_value(row[idx] if idx < len(row) else None)
                for idx, col_name in enumerate(safe_columns)
            }
            for row in exec_result.rows
        ]
        duration_ms = (monotonic() - start_time) * 1000.0
        self._emit_audit_log(
            user=user,
            tenant_id=effective_tenant_id,
            referenced_bindings=referenced_bindings,
            sql=guard_result.normalized_sql,
            duration_ms=duration_ms,
            row_count=len(safe_rows),
            outcome="OK",
        )

        return success_result(
            "run_sql",
            {
                "status": "OK",
                "sql": guard_result.normalized_sql,
                "columns": safe_columns,
                "rows": safe_rows,
                "row_count": len(safe_rows),
                "truncated": bool(exec_result.truncated),
                "referenced_tables": [
                    {
                        "view_name": b.view_name,
                        "document_id": b.document_id,
                        "version_id": b.version_id,
                        "file_name": b.file_name,
                        "sheet_name": b.sheet_name,
                        "table_name": b.table_name,
                    }
                    for b in referenced_bindings
                ],
            },
        )


def run_sql_tool_definition() -> ToolDefinition:
    """Định nghĩa schema tool `run_sql` (chỉ nhận tham số `sql`)."""
    return ToolDefinition(
        name="run_sql",
        description=(
            "Execute a read-only DuckDB SELECT query over authorized Excel tables in the user's scope. "
            "Pass only a single SELECT query using the provided table view names and column names."
        ),
        arguments_type=RunSqlArguments,
    )


def create_run_sql_handler(
    service: ExcelSqlService,
    *,
    user: UserContext | None = None,
    tenant_id: str | None = None,
    session_scope: Any = None,
) -> ToolHandler:
    """Tạo synchronous ToolHandler cho `run_sql` gắn cứng user/tenant/scope từ Backend."""

    def _handle_run_sql(arguments: object) -> ToolEnvelope:
        try:
            validated = validate_arguments("run_sql", arguments)
        except ToolContractError as exc:
            return failure_result("run_sql", exc.code)
        return service.execute_query(
            sql=str(validated["sql"]),
            user=user,
            tenant_id=tenant_id,
            session_scope=session_scope,
        )

    return _handle_run_sql
