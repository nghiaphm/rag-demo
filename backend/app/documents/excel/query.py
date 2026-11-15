"""Structured filtering and aggregation over validated .xlsx workbooks."""

from __future__ import annotations

import re
from typing import Any, Literal

from app.documents.excel.validation import read_workbook


ExcelOperation = Literal["rows", "count", "sum", "avg", "min", "max"]
_NUMERIC_CLEAN_RE = re.compile(r"[,$\s]")


def _find_column_index(columns: list[str], target: str) -> int:
    normalized = target.strip().lower()
    for idx, col in enumerate(columns):
        if (col or "").strip().lower() == normalized:
            return idx
    raise ValueError(f"Column not found: {target}")


def _parse_number(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = _NUMERIC_CLEAN_RE.sub("", str(raw).strip())
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def query_workbook_bytes(
    content: bytes,
    *,
    sheet_name: str | None = None,
    filter_column: str | None = None,
    filter_value: str | None = None,
    aggregate_column: str | None = None,
    operation: ExcelOperation = "rows",
    limit: int = 10,
) -> dict[str, Any]:
    """Run a bounded structured filter/aggregation query on an .xlsx workbook."""
    sheets = read_workbook(content)
    if not sheets:
        raise ValueError("Workbook has no readable sheets.")

    if sheet_name is not None:
        target_sheet = next(
            (s for s in sheets if s["name"].strip().lower() == sheet_name.strip().lower()),
            None,
        )
        if target_sheet is None:
            raise ValueError(f"Sheet not found: {sheet_name}")
    else:
        target_sheet = sheets[0]

    columns: list[str] = [
        col if col else f"Column {idx + 1}"
        for idx, col in enumerate(target_sheet["columns"])
    ]
    rows: list[tuple[int, list[Any]]] = list(target_sheet["rows"])

    if filter_column is not None:
        if filter_value is None:
            raise ValueError("filter_value is required when filter_column is provided.")
        filter_idx = _find_column_index(columns, filter_column)
        needle = filter_value.strip().lower()
        rows = [
            (row_idx, values)
            for row_idx, values in rows
            if filter_idx < len(values) and needle in str(values[filter_idx]).strip().lower()
        ]

    matched_count = len(rows)
    base: dict[str, Any] = {
        "sheet_name": target_sheet["name"],
        "operation": operation,
        "matched_count": matched_count,
    }

    if operation == "count":
        return base

    if operation == "rows":
        projected: list[dict[str, Any]] = []
        for row_idx, values in rows[:limit]:
            row_dict: dict[str, Any] = {"_row": row_idx}
            for idx, col_name in enumerate(columns):
                val = values[idx] if idx < len(values) else ""
                row_dict[col_name] = val[:200] if isinstance(val, str) else val
            projected.append(row_dict)
        base["columns"] = columns
        base["rows"] = projected
        base["truncated"] = matched_count > limit
        return base

    if aggregate_column is None:
        raise ValueError("aggregate_column is required for sum/avg/min/max.")

    agg_idx = _find_column_index(columns, aggregate_column)
    numbers: list[float] = []
    for _, values in rows:
        if agg_idx < len(values):
            parsed = _parse_number(values[agg_idx])
            if parsed is not None:
                numbers.append(parsed)

    if not numbers:
        base["aggregate_column"] = columns[agg_idx]
        base["numeric_count"] = 0
        base["value"] = None
        return base

    if operation == "sum":
        agg_value = round(sum(numbers), 4)
    elif operation == "avg":
        agg_value = round(sum(numbers) / len(numbers), 4)
    elif operation == "min":
        agg_value = round(min(numbers), 4)
    else:  # max
        agg_value = round(max(numbers), 4)

    base["aggregate_column"] = columns[agg_idx]
    base["numeric_count"] = len(numbers)
    base["value"] = agg_value
    return base
