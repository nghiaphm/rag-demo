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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
import json
import logging
import math
from pathlib import Path
import re
from time import monotonic
from typing import Any, Literal
import unicodedata

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


def _normalize_for_pattern_match(text: str) -> str:
    """Bỏ dấu tiếng Việt, chuyển chữ thường và chuẩn hóa khoảng trắng/ký tự đặc biệt thành '_'."""
    raw = (text or "").replace("đ", "d").replace("Đ", "d").lower()
    decomposed = unicodedata.normalize("NFD", raw)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    normalized = unicodedata.normalize("NFC", stripped)
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def is_sensitive_column(
    name: str,
    original_name: str = "",
    patterns: Sequence[str] | None = None,
) -> bool:
    """Kiểm tra cột có khớp danh sách từ khóa nhạy cảm (`EXCEL_SENSITIVE_COLUMN_PATTERNS`) hay không."""
    active_patterns = (
        patterns
        if patterns is not None
        else getattr(settings, "excel_sensitive_column_patterns", ())
    )
    if isinstance(active_patterns, str):
        active_patterns = [p.strip().lower() for p in active_patterns.split(",") if p.strip()]

    norm_name = _normalize_for_pattern_match(name)
    norm_original = _normalize_for_pattern_match(original_name)
    name_tokens = set(norm_name.split("_")) if norm_name else set()
    orig_tokens = set(norm_original.split("_")) if norm_original else set()

    for raw_pattern in active_patterns:
        pat = _normalize_for_pattern_match(str(raw_pattern))
        if not pat:
            continue
        if "_" in pat:
            if pat in norm_name or pat in norm_original:
                return True
        else:
            if (
                pat in name_tokens
                or pat in orig_tokens
                or pat in norm_name
                or pat in norm_original
            ):
                return True
    return False


def _sanitize_sensitive_description(col: TableColumnSchema) -> str:
    """Loại bỏ phần `giá trị mẫu: ...` khỏi description của cột nhạy cảm."""
    desc = col.description or ""
    cleaned = re.sub(r",?\s*giá trị mẫu:.*$", "", desc, flags=re.IGNORECASE).strip()
    if cleaned:
        return f"{cleaned} (ẩn giá trị mẫu vì cột nhạy cảm)"
    return f"Cột gốc '{col.original_name}', kiểu {col.data_type} (ẩn giá trị mẫu vì cột nhạy cảm)"


def _score_binding_relevance(binding: AuthorizedTableBinding, query_tokens: set[str]) -> int:
    if not query_tokens:
        return 0
    haystack_parts = [
        _normalize_for_pattern_match(binding.view_name),
        _normalize_for_pattern_match(binding.file_name),
        _normalize_for_pattern_match(binding.sheet_name),
        _normalize_for_pattern_match(binding.table_name),
    ]
    for col in binding.columns:
        haystack_parts.append(_normalize_for_pattern_match(col.name))
        haystack_parts.append(_normalize_for_pattern_match(col.original_name))
    haystack = " ".join(part for part in haystack_parts if part)
    score = 0
    for token in query_tokens:
        if token in haystack:
            score += 1
    return score


def _render_single_table_summary(
    binding: AuthorizedTableBinding,
    *,
    include_descriptions: bool,
    sample_rows_count: int,
    max_columns: int | None = None,
    sensitive_patterns: Sequence[str] | None = None,
) -> str:
    lines: list[str] = [
        (
            f"- View SQL: `{binding.view_name}` "
            f"(file: `{binding.file_name}`, sheet: `{binding.sheet_name}`, "
            f"số dòng: {binding.row_count})"
        )
    ]
    if binding.has_formula_values:
        lines.append(
            "  Ghi chú: Bảng có ô công thức Excel thiếu cached value (giá trị trong bảng là NULL)."
        )

    sensitive_col_names: set[str] = set()
    cols_to_show = (
        binding.columns[:max_columns]
        if max_columns is not None
        else binding.columns
    )
    col_lines: list[str] = []
    for col in cols_to_show:
        sensitive = is_sensitive_column(col.name, col.original_name, sensitive_patterns)
        if sensitive:
            sensitive_col_names.add(col.name)
        if include_descriptions:
            desc = (
                _sanitize_sensitive_description(col)
                if sensitive
                else (col.description or f"Cột gốc '{col.original_name}', kiểu {col.data_type}")
            )
            col_lines.append(
                f"    + `{col.name}` (tên gốc: '{col.original_name}', kiểu: {col.data_type}): {desc}"
            )
        else:
            col_lines.append(
                f"    + `{col.name}` ('{col.original_name}', {col.data_type})"
            )

    if col_lines:
        lines.append("  Các cột:")
        lines.extend(col_lines)
        if max_columns is not None and len(binding.columns) > max_columns:
            lines.append(f"    + ... ({len(binding.columns) - max_columns} cột khác đã rút gọn)")

    if sample_rows_count > 0 and binding.sample_rows:
        safe_samples: list[dict[str, Any]] = []
        for row in binding.sample_rows[:sample_rows_count]:
            filtered_row = {
                k: v for k, v in row.items() if k not in sensitive_col_names
            }
            if filtered_row:
                safe_samples.append(filtered_row)
        if safe_samples:
            lines.append(
                "  Dòng mẫu: " + json.dumps(safe_samples, ensure_ascii=False)
            )
    return "\n".join(lines)


def format_catalog_summary_for_prompt(
    bindings: Sequence[AuthorizedTableBinding],
    *,
    question: str = "",
    count_tokens: Callable[[str], int],
    max_tokens: int,
    sample_rows_limit: int | None = None,
    sensitive_patterns: Sequence[str] | None = None,
) -> str:
    """Sinh bản tóm tắt Table Catalog đã lọc quyền + che cột nhạy cảm + đảm bảo không vượt `max_tokens`."""
    if not bindings or max_tokens <= 0:
        return ""

    effective_samples = (
        int(sample_rows_limit)
        if sample_rows_limit is not None and sample_rows_limit >= 0
        else int(getattr(settings, "excel_catalog_sample_rows", 3))
    )
    query_norm = _normalize_for_pattern_match(question)
    query_tokens = {tok for tok in query_norm.split("_") if len(tok) >= 2}

    indexed_bindings = list(enumerate(bindings))
    indexed_bindings.sort(
        key=lambda item: (-_score_binding_relevance(item[1], query_tokens), item[0])
    )
    ordered_bindings = [b for _, b in indexed_bindings]
    header = "Danh mục bảng Excel được phép truy vấn bằng `run_sql`:"

    # Bước 1: Thử bản đầy đủ (mô tả cột + sample_rows) rồi giảm dần sample_rows -> bỏ mô tả cột.
    sample_steps = sorted({effective_samples, 1, 0}, reverse=True)
    for samples in sample_steps:
        if samples > effective_samples:
            continue
        for include_desc in (True, False):
            if include_desc is False and samples > 0:
                continue
            body = "\n".join(
                _render_single_table_summary(
                    b,
                    include_descriptions=include_desc,
                    sample_rows_count=samples,
                    sensitive_patterns=sensitive_patterns,
                )
                for b in ordered_bindings
            )
            candidate = f"{header}\n{body}"
            if count_tokens(candidate) <= max_tokens:
                return candidate

    # Bước 2: Rút gọn số bảng theo thứ tự khớp câu hỏi (chỉ giữ tên bảng + tên cột + kiểu).
    for table_limit in range(len(ordered_bindings) - 1, 0, -1):
        body = "\n".join(
            _render_single_table_summary(
                b,
                include_descriptions=False,
                sample_rows_count=0,
                sensitive_patterns=sensitive_patterns,
            )
            for b in ordered_bindings[:table_limit]
        )
        candidate = f"{header}\n{body}"
        if count_tokens(candidate) <= max_tokens:
            return candidate

    # Bước 3: Chỉ còn 1 bảng ưu tiên nhất, giảm dần số cột hiển thị cho tới khi vừa ngân sách.
    top_binding = ordered_bindings[0]
    for col_limit in range(len(top_binding.columns), 0, -1):
        body = _render_single_table_summary(
            top_binding,
            include_descriptions=False,
            sample_rows_count=0,
            max_columns=col_limit,
            sensitive_patterns=sensitive_patterns,
        )
        candidate = f"{header}\n{body}"
        if count_tokens(candidate) <= max_tokens:
            return candidate

    minimal = f"{header}\n- View SQL: `{top_binding.view_name}` (file: `{top_binding.file_name}`, sheet: `{top_binding.sheet_name}`)"
    if count_tokens(minimal) <= max_tokens:
        return minimal
    return ""


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
    collected_sources: list[dict[str, Any]] | None = None,
) -> ToolHandler:
    """Tạo synchronous ToolHandler cho `run_sql` gắn cứng user/tenant/scope từ Backend."""

    def _handle_run_sql(arguments: object) -> ToolEnvelope:
        try:
            validated = validate_arguments("run_sql", arguments)
        except ToolContractError as exc:
            return failure_result("run_sql", exc.code)
        envelope = service.execute_query(
            sql=str(validated["sql"]),
            user=user,
            tenant_id=tenant_id,
            session_scope=session_scope,
        )
        if envelope.get("ok") and collected_sources is not None:
            data = envelope.get("data") or {}
            normalized_sql = str(data.get("sql") or "")
            referenced_tables = data.get("referenced_tables") or []
            seen_keys = {
                (
                    s.get("document_id"),
                    s.get("version_id"),
                    s.get("sheet_name"),
                    s.get("source"),
                )
                for s in collected_sources
            }
            for ref in referenced_tables:
                if not isinstance(ref, dict):
                    continue
                view_name = str(ref.get("view_name") or ref.get("table_name") or "")
                source_label = (
                    f"sql:{view_name} | {normalized_sql[:180]}"
                    if normalized_sql
                    else f"sql:{view_name}"
                )
                entry = {
                    "file_name": ref.get("file_name"),
                    "sheet_name": ref.get("sheet_name"),
                    "document_id": ref.get("document_id"),
                    "version_id": ref.get("version_id"),
                    "source": source_label,
                }
                dedup_key = (
                    entry["document_id"],
                    entry["version_id"],
                    entry["sheet_name"],
                    entry["source"],
                )
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    collected_sources.append(entry)
        return envelope

    return _handle_run_sql


def create_excel_sql_service(
    database: Any,
    *,
    executor: SqlQueryExecutor | None = None,
) -> ExcelSqlService:
    """Factory khởi tạo `ExcelSqlService` với repository MongoDB và `DuckDBSqlExecutor`."""
    from app.documents.repository import MongoDocumentRepository

    effective_executor = executor
    if effective_executor is None:
        from app.infrastructure.duckdb_executor import create_duckdb_sql_executor

        effective_executor = create_duckdb_sql_executor()
    return ExcelSqlService(
        repository=MongoDocumentRepository(database),
        executor=effective_executor,
    )
