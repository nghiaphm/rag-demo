"""Kiểm duyệt và viết lại câu lệnh SQL bằng sqlglot (dialect DuckDB) cho tool `run_sql`.

Module này hoàn toàn thuần (pure logic, không I/O, không import `infrastructure/`):
1. Parse SQL bằng `sqlglot` dialect `duckdb`, ép đúng 1 statement.
2. Chỉ cho phép `SELECT` / `UNION` / `INTERSECT` / `EXCEPT` (kể cả CTE `WITH`).
3. Whitelist tuyệt đối bảng trong `FROM`/`JOIN`: cấm `schema.table`, cấm chuỗi đường dẫn
   `FROM 'file.parquet'`, cấm mọi table-valued function (`read_parquet`, `read_csv`, `glob`, `unnest`, `range`, ...).
4. Blocklist bổ sung cho các scalar/system function nhạy cảm (`getenv`, `current_setting`, `duckdb_*`, `pragma_*`, `read_*`, `parquet_*`).
5. Tự động chèn hoặc hạ `LIMIT <= max_rows` ở mức AST (bọc `SELECT * FROM (...) LIMIT n` cho `UNION`/`INTERSECT`/`EXCEPT`)
   và sinh lại chuỗi SQL chuẩn từ AST.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

_VALID_VIEW_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")

_BLOCKED_FUNCTION_NAMES = frozenset({
    "getenv",
    "current_setting",
    "current_catalog",
    "current_schema",
    "current_user",
    "session_user",
    "user",
    "version",
    "read_parquet",
    "read_csv",
    "read_csv_auto",
    "read_json",
    "read_json_auto",
    "read_json_objects",
    "read_ndjson",
    "read_ndjson_auto",
    "read_ndjson_objects",
    "read_text",
    "read_blob",
    "glob",
    "parse_path",
    "parse_dirpath",
    "parse_filename",
    "parquet_scan",
    "parquet_metadata",
    "parquet_schema",
    "parquet_file_metadata",
    "parquet_kv_metadata",
    "sniff_csv",
    "query",
    "query_table",
    "sqlite_scan",
    "sqlite_attach",
    "postgres_scan",
    "mysql_scan",
    "iceberg_scan",
    "delta_scan",
    "excel_scan",
    "st_read",
})

_BLOCKED_FUNCTION_PREFIXES = (
    "duckdb_",
    "pragma_",
    "read_",
    "parquet_",
    "httpfs_",
    "s3_",
)

_FORBIDDEN_AST_NODE_TYPES: tuple[type[exp.Expression], ...] = tuple(
    node_type
    for node_type in (
        getattr(exp, "Insert", None),
        getattr(exp, "Update", None),
        getattr(exp, "Delete", None),
        getattr(exp, "Merge", None),
        getattr(exp, "Create", None),
        getattr(exp, "Drop", None),
        getattr(exp, "Alter", None),
        getattr(exp, "Command", None),
        getattr(exp, "Pragma", None),
        getattr(exp, "Set", None),
        getattr(exp, "Copy", None),
        getattr(exp, "Attach", None),
        getattr(exp, "Detach", None),
        getattr(exp, "LoadData", None),
        getattr(exp, "Export", None),
        getattr(exp, "Install", None),
        getattr(exp, "Use", None),
        getattr(exp, "Transaction", None),
        getattr(exp, "Commit", None),
        getattr(exp, "Rollback", None),
        getattr(exp, "Into", None),
        getattr(exp, "Lock", None),
        getattr(exp, "TableSample", None),
    )
    if node_type is not None
)


@dataclass(frozen=True, slots=True)
class SqlGuardResult:
    ok: bool
    normalized_sql: str | None
    referenced_tables: tuple[str, ...]
    reason: str | None = None

    def __iter__(self) -> Iterator[object]:
        yield self.ok
        yield self.normalized_sql
        yield self.referenced_tables
        yield self.reason


def _format_allowed_views_hint(allowed_map: dict[str, str]) -> str:
    if not allowed_map:
        return "Hiện không có bảng hợp lệ nào khả dụng."
    sorted_views = sorted(allowed_map.values())
    return f"Bảng hợp lệ: {', '.join(sorted_views)}."


def _extract_function_name(func_node: exp.Expression) -> str:
    if isinstance(func_node, exp.Anonymous):
        return str(func_node.name or "").strip().lower()
    if isinstance(func_node, exp.Func):
        sql_name = getattr(func_node, "sql_name", None)
        callable_name = sql_name() if callable(sql_name) else ""
        raw_name = func_node.name or callable_name or func_node.key
        return str(raw_name or "").strip().lower()
    return ""


def _is_blocked_function_name(func_name: str) -> bool:
    if not func_name:
        return False
    lowered = func_name.strip().lower()
    if lowered in _BLOCKED_FUNCTION_NAMES:
        return True
    return any(lowered.startswith(prefix) for prefix in _BLOCKED_FUNCTION_PREFIXES)


def _clamp_select_limit(select_node: exp.Select, max_rows: int) -> exp.Select:
    limit_node = select_node.args.get("limit")
    if limit_node is None:
        return select_node.limit(max_rows)

    limit_expr = getattr(limit_node, "expression", None)
    if isinstance(limit_expr, exp.Literal) and limit_expr.is_int:
        try:
            val = int(limit_expr.this)
        except (TypeError, ValueError):
            return select_node.limit(max_rows)
        if val <= max_rows:
            return select_node
    return select_node.limit(max_rows)


def _enforce_ast_row_limit(statement: exp.Expression, max_rows: int) -> exp.Expression:
    if isinstance(statement, exp.Select):
        return _clamp_select_limit(statement, max_rows)

    if isinstance(statement, (exp.Union, exp.Intersect, exp.Except)):
        # Nếu bản thân SetOperation có LIMIT > max_rows thì hạ xuống trước khi bọc
        limit_node = statement.args.get("limit")
        if limit_node is not None:
            limit_expr = getattr(limit_node, "expression", None)
            if not (
                isinstance(limit_expr, exp.Literal)
                and limit_expr.is_int
                and int(limit_expr.this) <= max_rows
            ):
                statement.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))

        # Bọc SELECT * FROM (...) AS _set_q LIMIT max_rows (nếu có WITH ở cấp cao nhất thì nâng WITH ra ngoài)
        outer_with = statement.args.get("with_") or statement.args.get("with")
        inner_stmt = statement.copy()
        if outer_with is not None:
            inner_stmt.set("with_", None)
            inner_stmt.set("with", None)

        wrapped = exp.select("*").from_(
            exp.Subquery(
                this=inner_stmt,
                alias=exp.TableAlias(this=exp.to_identifier("_bounded_set")),
            )
        ).limit(max_rows)
        if outer_with is not None:
            wrapped.set("with_", outer_with)
        return wrapped

    return statement


def validate_and_rewrite_sql(
    sql: str,
    allowed_views: Iterable[str],
    *,
    max_rows: int = 200,
) -> SqlGuardResult:
    """Kiểm duyệt câu lệnh SQL bằng sqlglot (dialect duckdb) và trả về SQL đã chuẩn hóa từ AST."""
    if not isinstance(sql, str) or not sql.strip():
        return SqlGuardResult(
            ok=False,
            normalized_sql=None,
            referenced_tables=(),
            reason="Câu lệnh SQL không được rỗng.",
        )
    if max_rows < 1:
        raise ValueError("max_rows phải >= 1")

    allowed_map: dict[str, str] = {}
    for view in allowed_views:
        if not isinstance(view, str):
            continue
        cleaned = view.strip()
        if cleaned and _VALID_VIEW_NAME_RE.fullmatch(cleaned):
            allowed_map[cleaned.lower()] = cleaned

    if not allowed_map:
        return SqlGuardResult(
            ok=False,
            normalized_sql=None,
            referenced_tables=(),
            reason="Hiện không có bảng dữ liệu nào được cấp quyền để truy vấn.",
        )

    try:
        parsed_statements = sqlglot.parse(
            sql,
            read="duckdb",
            error_level=sqlglot.ErrorLevel.RAISE,
        )
    except (SqlglotError, Exception):
        return SqlGuardResult(
            ok=False,
            normalized_sql=None,
            referenced_tables=(),
            reason="Cú pháp SQL không hợp lệ với DuckDB. Chỉ chấp nhận một câu lệnh SELECT hợp lệ.",
        )

    statements = [stmt for stmt in parsed_statements if stmt is not None]
    if len(statements) != 1:
        return SqlGuardResult(
            ok=False,
            normalized_sql=None,
            referenced_tables=(),
            reason="Chỉ cho phép thực thi đúng 1 câu lệnh SELECT duy nhất.",
        )

    root = statements[0]
    if not isinstance(root, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return SqlGuardResult(
            ok=False,
            normalized_sql=None,
            referenced_tables=(),
            reason="Chỉ cho phép câu lệnh truy vấn đọc (SELECT / UNION / INTERSECT / EXCEPT).",
        )

    # 1. Chặn mọi node DDL/DML/Admin/Into/Sample/Lock ở bất kỳ đâu trong AST
    for node in root.walk():
        if isinstance(node, _FORBIDDEN_AST_NODE_TYPES):
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason="Câu lệnh chứa biểu thức bị cấm (chỉ cho phép SELECT thuần túy).",
            )
        if isinstance(node, exp.Select) and (
            node.args.get("into") is not None or node.args.get("locks")
        ):
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason="Không cho phép SELECT INTO hoặc khóa dòng (FOR UPDATE).",
            )
        if isinstance(node, exp.Limit):
            limit_expr = getattr(node, "expression", None)
            if isinstance(limit_expr, exp.Literal) and limit_expr.is_int:
                if int(limit_expr.this) < 0:
                    return SqlGuardResult(
                        ok=False,
                        normalized_sql=None,
                        referenced_tables=(),
                        reason="Giá trị LIMIT không được âm.",
                    )

    # 2. Thu thập danh sách alias CTE hợp lệ và chặn CTE trùng tên che giấu bảng thật
    cte_names: set[str] = set()
    for cte in root.find_all(exp.CTE):
        alias_name = (cte.alias_or_name or "").strip().lower()
        if not alias_name:
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason="CTE trong mệnh đề WITH phải có tên hợp lệ.",
            )
        if alias_name in allowed_map or alias_name in cte_names:
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason=(
                    f"Tên CTE '{alias_name}' không được trùng với tên bảng dữ liệu hoặc CTE khác. "
                    f"{_format_allowed_views_hint(allowed_map)}"
                ),
            )
        cte_names.add(alias_name)

    # 3. Kiểm tra mọi mệnh đề FROM và JOIN chỉ chứa Table đơn giản hoặc Subquery
    for clause in (*root.find_all(exp.From), *root.find_all(exp.Join)):
        target = clause.this
        if not isinstance(target, (exp.Table, exp.Subquery)):
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason=(
                    "Mệnh đề FROM/JOIN chỉ được phép truy vấn trực tiếp từ bảng được cấp quyền "
                    f"hoặc subquery; không hỗ trợ hàm tạo bảng. {_format_allowed_views_hint(allowed_map)}"
                ),
            )
        for extra_expr in clause.expressions:
            if not isinstance(extra_expr, (exp.Table, exp.Subquery)):
                return SqlGuardResult(
                    ok=False,
                    normalized_sql=None,
                    referenced_tables=(),
                    reason=(
                        "Mệnh đề FROM không hỗ trợ hàm tạo bảng hoặc đường dẫn trực tiếp. "
                        f"{_format_allowed_views_hint(allowed_map)}"
                    ),
                )

    # 4. Kiểm tra blocklist cho mọi lời gọi hàm trong toàn bộ AST
    for func_node in root.find_all(exp.Func):
        for candidate_name in (
            _extract_function_name(func_node),
            str(func_node.key or "").strip().lower(),
        ):
            if _is_blocked_function_name(candidate_name):
                return SqlGuardResult(
                    ok=False,
                    normalized_sql=None,
                    referenced_tables=(),
                    reason="Hàm hệ thống hoặc hàm đọc file trực tiếp không được phép sử dụng.",
                )

    # 5. Kiểm tra WHITELIST cho toàn bộ exp.Table trong AST (duyệt DFS theo thứ tự xuất hiện trong câu SQL)
    referenced: list[str] = []
    seen_referenced: set[str] = set()
    all_tables = [node for node in root.walk(bfs=False) if isinstance(node, exp.Table)]
    if not all_tables:
        return SqlGuardResult(
            ok=False,
            normalized_sql=None,
            referenced_tables=(),
            reason=f"Câu lệnh SELECT phải truy vấn ít nhất một bảng được cấp quyền. {_format_allowed_views_hint(allowed_map)}",
        )

    for table in all_tables:
        if table.db or table.catalog:
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason=(
                    "Không cho phép sử dụng tiền tố schema hoặc catalog (ví dụ schema.table). "
                    f"{_format_allowed_views_hint(allowed_map)}"
                ),
            )
        if table.args.get("pivots") or table.args.get("sample"):
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason="Không hỗ trợ mệnh đề SAMPLE hoặc PIVOT trực tiếp trên bảng.",
            )
        inner = table.this
        if not isinstance(inner, exp.Identifier):
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason=(
                    "Chỉ cho phép truy vấn tên bảng hợp lệ trong danh sách, không chấp nhận đường dẫn hoặc hàm bảng. "
                    f"{_format_allowed_views_hint(allowed_map)}"
                ),
            )
        raw_table_name = (inner.name or "").strip()
        if not raw_table_name or not _VALID_VIEW_NAME_RE.fullmatch(raw_table_name):
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason=(
                    f"Tên bảng '{raw_table_name}' không hợp lệ. {_format_allowed_views_hint(allowed_map)}"
                ),
            )

        lowered_name = raw_table_name.lower()
        if lowered_name in cte_names and lowered_name not in allowed_map:
            continue

        canonical_view = allowed_map.get(lowered_name)
        if canonical_view is None:
            return SqlGuardResult(
                ok=False,
                normalized_sql=None,
                referenced_tables=(),
                reason=(
                    f"Bảng '{raw_table_name}' không có trong danh sách được phép truy cập. "
                    f"{_format_allowed_views_hint(allowed_map)}"
                ),
            )

        # Chuẩn hóa tên bảng trong AST về đúng tên canonical
        table.set("this", exp.to_identifier(canonical_view))
        if canonical_view not in seen_referenced:
            seen_referenced.add(canonical_view)
            referenced.append(canonical_view)

    if not referenced:
        return SqlGuardResult(
            ok=False,
            normalized_sql=None,
            referenced_tables=(),
            reason=(
                "Câu lệnh phải tham chiếu ít nhất một bảng dữ liệu thực trong danh sách được cấp quyền. "
                f"{_format_allowed_views_hint(allowed_map)}"
            ),
        )

    # 6. Tự động chèn hoặc hạ LIMIT <= max_rows ở mức AST và sinh lại SQL (loại bỏ toàn bộ comment)
    rewritten_ast = _enforce_ast_row_limit(root.copy(), max_rows=max_rows)
    rewritten_sql = rewritten_ast.sql(dialect="duckdb", comments=False)

    return SqlGuardResult(
        ok=True,
        normalized_sql=rewritten_sql,
        referenced_tables=tuple(sorted(referenced)),
        reason=None,
    )
