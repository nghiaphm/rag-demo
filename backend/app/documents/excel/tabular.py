"""Chuẩn hóa bảng Excel (.xlsx) thành Parquet bytes và metadata Table Catalog.

Module này hoàn toàn thuần (pure logic, không I/O xuống Storage hay MongoDB):
- Tái sử dụng `read_workbook()` để giữ nguyên 100% giới hạn an toàn chống zip-bomb/macro.
- Đọc cached value cho ô công thức (`data_only=True, read_only=True, keep_links=False`);
  ô công thức không có cached value được gán `NULL` và đánh dấu `has_formula_values=True`.
- Dò dòng header thông minh (bỏ dòng tiêu đề đơn lẻ phía trên, chọn dòng đầu tiên có >= 2 ô text khác nhau).
- Chuẩn hóa tên bảng và tên cột về `snake_case` ASCII duy nhất, khớp `[a-z][a-z0-9_]{0,62}`.
- Suy luận kiểu dữ liệu cột (`INT64`, `DOUBLE`, `BOOLEAN`, `DATE`, `TIMESTAMP`, `VARCHAR`)
  bảo toàn mã có số 0 đứng đầu (`"00123"`), số nguyên lớn và định dạng số kiểu Việt Nam nhất quán 100%.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from io import BytesIO
import logging
import math
import re
from typing import Any, Literal
import unicodedata

from openpyxl import load_workbook
import pyarrow as pa
import pyarrow.parquet as pq

from app.documents.excel.validation import (
    MAX_CELL_CHARS,
    WorkbookError,
    read_workbook,
)
from app.shared.config import settings

logger = logging.getLogger(__name__)

ColumnDataType = Literal["INT64", "DOUBLE", "BOOLEAN", "DATE", "TIMESTAMP", "VARCHAR"]

FREE_TEXT_MIN_AVG_CHARS: int = 30
FREE_TEXT_MIN_WORDS_PER_CELL: int = 5
FREE_TEXT_MIN_MULTIWORD_RATIO: float = 0.5
ID_CODE_MIN_UNIQUE_RATIO: float = 0.8
ID_CODE_MAX_AVG_CHARS: int = 24
SHORT_CATEGORY_MAX_DISTINCT: int = 10
SHORT_CATEGORY_MAX_UNIQUE_RATIO: float = 0.4
SHORT_CATEGORY_MAX_AVG_CHARS: int = 25
_ID_COLUMN_NAME_TOKENS = frozenset({"id", "ma", "code", "sku", "uuid", "mst", "stt"})

_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_LEADING_ZERO_CODE_RE = re.compile(r"^[-+]?0\d+$")
_PLAIN_INT_RE = re.compile(r"^[-+]?\d+$")
_STANDARD_FLOAT_RE = re.compile(r"^[-+]?\d+\.\d+$")
_VN_THOUSANDS_INT_RE = re.compile(r"^[-+]?\d{1,3}(?:\.\d{3})+$")
_VN_DECIMAL_RE = re.compile(r"^[-+]?(?:\d{1,3}(?:\.\d{3})+|\d+),\d+$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VN_SLASH_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:?\d{2})?$"
)

_EXCEL_ERROR_TOKENS = frozenset({
    "#VALUE!",
    "#REF!",
    "#DIV/0!",
    "#NAME?",
    "#N/A",
    "#NUM!",
    "#NULL!",
    "#GETTING_DATA",
})

_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1
_FLOAT64_SAFE_INT_MAX = 1 << 53
_MAX_SAMPLE_CELL_CHARS = 100
_MAX_DESC_SAMPLE_CHARS = 40


@dataclass(frozen=True, slots=True)
class NormalizedColumnSchema:
    name: str
    original_name: str
    data_type: ColumnDataType
    nullable: bool
    description: str
    has_formula_values: bool = False
    is_free_text: bool = False

    @property
    def type(self) -> ColumnDataType:
        return self.data_type


@dataclass(frozen=True, slots=True)
class NormalizedExcelTable:
    table_name: str
    sheet_name: str
    parquet_bytes: bytes
    row_count: int
    columns: tuple[NormalizedColumnSchema, ...]
    sample_rows: tuple[dict[str, Any], ...]
    has_formula_values: bool = False


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "d")


def _normalize_base_identifier(raw: str, *, fallback: str, digit_prefix: str) -> str:
    ascii_text = _strip_accents(raw).lower()
    slug = _NON_ALNUM_RE.sub("_", ascii_text).strip("_")
    if not slug:
        slug = fallback
    if slug[0].isdigit():
        slug = f"{digit_prefix}{slug}"
    slug = slug[:63].rstrip("_")
    if not slug or not _IDENTIFIER_PATTERN.fullmatch(slug):
        slug = fallback
    return slug


def _allocate_unique_identifier(base: str, used: set[str]) -> str:
    candidate = base[:63].rstrip("_")
    if candidate not in used:
        used.add(candidate)
        return candidate

    counter = 2
    while True:
        suffix = f"_{counter}"
        max_base_len = 63 - len(suffix)
        trimmed_base = base[:max_base_len].rstrip("_")
        if not trimmed_base:
            trimmed_base = "t"
        candidate = f"{trimmed_base}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


def normalize_table_name(sheet_name: str, used_names: set[str] | None = None) -> str:
    """Chuẩn hóa tên sheet thành tên bảng snake_case ASCII duy nhất khớp `[a-z][a-z0-9_]{0,62}`."""
    used = used_names if used_names is not None else set()
    base = _normalize_base_identifier(sheet_name or "", fallback="sheet", digit_prefix="t_")
    return _allocate_unique_identifier(base, used)


def normalize_column_name(
    header_text: str,
    col_index: int,
    used_names: set[str] | None = None,
) -> tuple[str, str]:
    """Chuẩn hóa tên cột thành snake_case ASCII duy nhất và trả về `(name, original_name)`."""
    used = used_names if used_names is not None else set()
    fallback = f"col_{col_index}"
    cleaned_original = (header_text or "").strip()
    if not cleaned_original:
        return _allocate_unique_identifier(fallback, used), fallback

    base = _normalize_base_identifier(cleaned_original, fallback=fallback, digit_prefix="c_")
    return _allocate_unique_identifier(base, used), cleaned_original


def _is_header_text_token(raw_cell: str, native_value: Any) -> bool:
    """Kiểm tra một ô có phải nhãn text hợp lệ để nhận diện dòng header hay không."""
    token = (raw_cell or "").strip()
    if not token or token.startswith("="):
        return False
    if token.upper() in _EXCEL_ERROR_TOKENS:
        return False
    if isinstance(native_value, (int, float, bool, date, datetime, time)):
        return False
    if _PLAIN_INT_RE.fullmatch(token) or _STANDARD_FLOAT_RE.fullmatch(token):
        return False
    if _VN_THOUSANDS_INT_RE.fullmatch(token) or _VN_DECIMAL_RE.fullmatch(token):
        return False
    if _ISO_DATE_RE.fullmatch(token) or _VN_SLASH_DATE_RE.fullmatch(token):
        return False
    return True


def _detect_header_position(
    all_rows: list[tuple[int, list[str]]],
    native_rows_by_index: dict[int, list[Any]],
) -> int | None:
    """Chọn dòng đầu tiên có >= 2 ô text khác nhau làm header."""
    for pos, (row_index, raw_cells) in enumerate(all_rows):
        native_row = native_rows_by_index.get(row_index, [])
        distinct_texts: set[str] = set()
        for idx, cell_text in enumerate(raw_cells):
            native_val = native_row[idx] if idx < len(native_row) else None
            if _is_header_text_token(cell_text, native_val):
                distinct_texts.add(cell_text.strip().lower())
        if len(distinct_texts) >= 2:
            return pos
    return None


def _read_cached_native_sheets(content: bytes) -> dict[str, dict[int, list[Any]]]:
    """Đọc giá trị cached (`data_only=True, read_only=True, keep_links=False`) sau khi đã qua `read_workbook()`."""
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
    try:
        result: dict[str, dict[int, list[Any]]] = {}
        for sheet in workbook.worksheets:
            rows_map: dict[int, list[Any]] = {}
            for index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                validated_row: list[Any] = []
                for val in row:
                    if isinstance(val, float) and not math.isfinite(val):
                        raise WorkbookError("Workbook chứa giá trị số không hợp lệ.")
                    if isinstance(val, str) and len(val) > MAX_CELL_CHARS:
                        raise WorkbookError("Ô Excel vượt quá giới hạn 32767 ký tự.")
                    validated_row.append(val)
                rows_map[index] = validated_row
            result[sheet.title] = rows_map
        return result
    finally:
        workbook.close()


@dataclass(frozen=True, slots=True)
class _CellSample:
    raw_text: str
    native_value: Any
    is_formula: bool


def _resolve_effective_cell(sample: _CellSample) -> Any:
    """Chuẩn hóa giá trị ô (xử lý cached value của công thức và chuỗi rỗng -> None)."""
    if sample.is_formula:
        val = sample.native_value
        if val is None:
            return None
        if isinstance(val, str):
            stripped = val.strip()
            if not stripped or stripped.startswith("=") or stripped.upper() in _EXCEL_ERROR_TOKENS:
                return None
            return stripped
        return val

    raw_stripped = sample.raw_text.strip()
    if not raw_stripped:
        return None
    val = sample.native_value
    if val is None:
        return None
    if isinstance(val, str):
        stripped = val.strip()
        return stripped if stripped else None
    return val


def _has_leading_zero_code(values: list[Any]) -> bool:
    for val in values:
        if isinstance(val, str) and _LEADING_ZERO_CODE_RE.fullmatch(val.strip()):
            return True
    return False


def _try_parse_booleans(values: list[Any]) -> list[bool | None] | None:
    parsed: list[bool | None] = []
    for val in values:
        if val is None:
            parsed.append(None)
        elif isinstance(val, bool):
            parsed.append(val)
        elif isinstance(val, str):
            lowered = val.strip().lower()
            if lowered == "true":
                parsed.append(True)
            elif lowered == "false":
                parsed.append(False)
            else:
                return None
        else:
            return None
    return parsed


def _is_lossless_float64_decimal(dec: Decimal, text_digits: int) -> bool:
    if text_digits > 15:
        return False
    as_float = float(dec)
    if not math.isfinite(as_float):
        return False
    return True


def _try_parse_standard_numbers(
    values: list[Any],
) -> tuple[Literal["INT64", "DOUBLE"], list[int | float | None]] | None:
    """Suy luận INT64 hoặc DOUBLE chuẩn (không áp dụng cho chuỗi định dạng số VN)."""
    int_candidates: list[int | None] = []
    float_candidates: list[float | None] = []
    all_int = True

    for val in values:
        if val is None:
            int_candidates.append(None)
            float_candidates.append(None)
            continue
        if isinstance(val, bool):
            return None
        if isinstance(val, int):
            if not (_INT64_MIN <= val <= _INT64_MAX):
                return None
            int_candidates.append(val)
            float_candidates.append(float(val) if abs(val) <= _FLOAT64_SAFE_INT_MAX else 0.0)
            continue
        if isinstance(val, float):
            if not math.isfinite(val):
                return None
            all_int = False
            float_candidates.append(val)
            continue
        if isinstance(val, str):
            token = val.strip()
            if _LEADING_ZERO_CODE_RE.fullmatch(token):
                return None
            if _PLAIN_INT_RE.fullmatch(token):
                int_val = int(token)
                if not (_INT64_MIN <= int_val <= _INT64_MAX):
                    return None
                int_candidates.append(int_val)
                float_candidates.append(
                    float(int_val) if abs(int_val) <= _FLOAT64_SAFE_INT_MAX else 0.0
                )
                continue
            # Nếu khớp định dạng hàng nghìn kiểu VN ("1.250.000") thì để nhánh VN xử lý
            if _VN_THOUSANDS_INT_RE.fullmatch(token):
                return None
            if _STANDARD_FLOAT_RE.fullmatch(token):
                significant_digits = len(token.lstrip("+-").replace(".", "").lstrip("0"))
                try:
                    dec = Decimal(token)
                except InvalidOperation:
                    return None
                if not _is_lossless_float64_decimal(dec, significant_digits):
                    return None
                all_int = False
                float_candidates.append(float(dec))
                continue
            return None
        return None

    if all_int:
        return "INT64", int_candidates

    # Khi nâng cả cột lên DOUBLE, đảm bảo không có số nguyên lớn bị mất độ chính xác (> 2^53)
    for val in values:
        if isinstance(val, int) and not isinstance(val, bool) and abs(val) > _FLOAT64_SAFE_INT_MAX:
            return None
        if isinstance(val, str) and _PLAIN_INT_RE.fullmatch(val.strip()):
            if abs(int(val.strip())) > _FLOAT64_SAFE_INT_MAX:
                return None

    return "DOUBLE", float_candidates


def _try_parse_vn_numbers(
    values: list[Any],
) -> tuple[Literal["INT64", "DOUBLE"], list[int | float | None]] | None:
    """Chuyển đổi định dạng số kiểu VN ('1.250.000,5') CHỈ KHI 100% giá trị trong cột nhất quán."""
    has_vn_formatted_str = any(
        isinstance(v, str)
        and (
            bool(_VN_THOUSANDS_INT_RE.fullmatch(v.strip()))
            or bool(_VN_DECIMAL_RE.fullmatch(v.strip()))
        )
        for v in values
        if v is not None
    )
    if not has_vn_formatted_str:
        return None

    int_candidates: list[int | None] = []
    float_candidates: list[float | None] = []
    all_int = True

    for val in values:
        if val is None:
            int_candidates.append(None)
            float_candidates.append(None)
            continue
        if isinstance(val, str):
            token = val.strip()
            if _LEADING_ZERO_CODE_RE.fullmatch(token):
                return None
            if _VN_THOUSANDS_INT_RE.fullmatch(token):
                normalized = token.replace(".", "")
                int_val = int(normalized)
                if not (_INT64_MIN <= int_val <= _INT64_MAX):
                    return None
                int_candidates.append(int_val)
                float_candidates.append(
                    float(int_val) if abs(int_val) <= _FLOAT64_SAFE_INT_MAX else 0.0
                )
                continue
            if _VN_DECIMAL_RE.fullmatch(token):
                normalized = token.replace(".", "").replace(",", ".")
                significant_digits = len(normalized.lstrip("+-").replace(".", "").lstrip("0"))
                try:
                    dec = Decimal(normalized)
                except InvalidOperation:
                    return None
                if not _is_lossless_float64_decimal(dec, significant_digits):
                    return None
                all_int = False
                float_candidates.append(float(dec))
                continue
            return None
        return None

    if all_int:
        return "INT64", int_candidates

    for val in values:
        if isinstance(val, str) and _VN_THOUSANDS_INT_RE.fullmatch(val.strip()):
            if abs(int(val.strip().replace(".", ""))) > _FLOAT64_SAFE_INT_MAX:
                return None

    return "DOUBLE", float_candidates


def _try_parse_dates_or_timestamps(
    values: list[Any],
    samples: list[_CellSample],
) -> tuple[Literal["DATE", "TIMESTAMP"], list[date | datetime | None]] | None:
    dates: list[date | None] = []
    timestamps: list[datetime | None] = []
    has_time_component = False

    for val, sample in zip(values, samples, strict=True):
        if val is None:
            dates.append(None)
            timestamps.append(None)
            continue
        if isinstance(val, datetime):
            raw = sample.raw_text.strip()
            is_midnight = (
                val.hour == 0
                and val.minute == 0
                and val.second == 0
                and val.microsecond == 0
            )
            # Nếu người dùng gõ chuỗi timestamp rõ ràng có giờ/phút hoặc giờ khác 00:00:00
            if not is_midnight:
                has_time_component = True
            dates.append(val.date())
            timestamps.append(val.replace(tzinfo=None))
            continue
        if isinstance(val, date):
            dates.append(val)
            timestamps.append(datetime.combine(val, time.min))
            continue
        if isinstance(val, str):
            token = val.strip()
            if _ISO_DATE_RE.fullmatch(token):
                try:
                    d = date.fromisoformat(token)
                except ValueError:
                    return None
                dates.append(d)
                timestamps.append(datetime.combine(d, time.min))
                continue
            if _VN_SLASH_DATE_RE.fullmatch(token):
                try:
                    d = datetime.strptime(token, "%d/%m/%Y").date()
                except ValueError:
                    return None
                dates.append(d)
                timestamps.append(datetime.combine(d, time.min))
                continue
            if _ISO_TIMESTAMP_RE.fullmatch(token):
                try:
                    normalized_ts = token.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(normalized_ts)
                except ValueError:
                    return None
                has_time_component = True
                naive_dt = dt.replace(tzinfo=None)
                dates.append(naive_dt.date())
                timestamps.append(naive_dt)
                continue
            return None
        return None

    if has_time_component:
        return "TIMESTAMP", timestamps
    return "DATE", dates


def _format_value_for_varchar(val: Any, sample: _CellSample) -> str | None:
    if val is None:
        return None
    if not sample.is_formula and sample.raw_text.strip():
        return sample.raw_text.strip()
    if isinstance(val, (date, datetime, time)):
        return val.isoformat()
    return str(val).strip()


def _infer_column_type_and_values(
    samples: list[_CellSample],
) -> tuple[ColumnDataType, list[Any], bool, bool]:
    """Suy luận `(data_type, typed_values, nullable, has_formula_values)` cho 1 cột."""
    has_formula = any(s.is_formula for s in samples)
    effective_values = [_resolve_effective_cell(s) for s in samples]
    nullable = any(v is None for v in effective_values)
    non_null = [v for v in effective_values if v is not None]

    if not non_null:
        return "VARCHAR", [None] * len(samples), True, has_formula

    if _has_leading_zero_code(non_null):
        varchar_vals = [
            _format_value_for_varchar(v, s)
            for v, s in zip(effective_values, samples, strict=True)
        ]
        return "VARCHAR", varchar_vals, nullable, has_formula

    bool_parsed = _try_parse_booleans(effective_values)
    if bool_parsed is not None:
        return "BOOLEAN", bool_parsed, nullable, has_formula

    std_num = _try_parse_standard_numbers(effective_values)
    if std_num is not None:
        return std_num[0], std_num[1], nullable, has_formula

    vn_num = _try_parse_vn_numbers(effective_values)
    if vn_num is not None:
        return vn_num[0], vn_num[1], nullable, has_formula

    dt_parsed = _try_parse_dates_or_timestamps(effective_values, samples)
    if dt_parsed is not None:
        return dt_parsed[0], dt_parsed[1], nullable, has_formula

    varchar_vals = [
        _format_value_for_varchar(v, s)
        for v, s in zip(effective_values, samples, strict=True)
    ]
    return "VARCHAR", varchar_vals, nullable, has_formula


def _format_sample_scalar(value: Any, *, max_chars: int = _MAX_SAMPLE_CELL_CHARS) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()[:max_chars]
    text = str(value)
    return text[:max_chars]


def _build_column_description(
    original_name: str,
    data_type: ColumnDataType,
    typed_values: list[Any],
    *,
    has_formula_values: bool,
) -> str:
    """Sinh mô tả cột theo rule: tên cột gốc + kiểu + tối đa 3 giá trị mẫu (không gọi LLM)."""
    seen: set[str] = set()
    examples: list[str] = []
    for val in typed_values:
        if val is None:
            continue
        rendered = str(_format_sample_scalar(val, max_chars=_MAX_DESC_SAMPLE_CHARS)).strip()
        if not rendered or rendered in seen:
            continue
        seen.add(rendered)
        examples.append(rendered)
        if len(examples) >= 3:
            break

    formula_note = ", có chứa công thức" if has_formula_values else ""
    if examples:
        return (
            f"Cột '{original_name}' (kiểu {data_type}{formula_note}), "
            f"ví dụ: {', '.join(examples)}"
        )
    return f"Cột '{original_name}' (kiểu {data_type}{formula_note}, chưa có giá trị mẫu)"


def _arrow_type_for(data_type: ColumnDataType) -> pa.DataType:
    if data_type == "INT64":
        return pa.int64()
    if data_type == "DOUBLE":
        return pa.float64()
    if data_type == "BOOLEAN":
        return pa.bool_()
    if data_type == "DATE":
        return pa.date32()
    if data_type == "TIMESTAMP":
        return pa.timestamp("us")
    return pa.string()


def extract_workbook_tables(
    content: bytes,
    *,
    content_type: str | None = None,
    sample_rows_limit: int = 3,
    compression: Literal["snappy", "zstd"] = "snappy",
) -> list[NormalizedExcelTable]:
    """Chuẩn hóa toàn bộ các sheet hợp lệ của workbook thành danh sách bảng Parquet + Catalog metadata."""
    # Bước 1: Kiểm tra toàn bộ giới hạn an toàn qua read_workbook() (data_only=False)
    raw_sheets = read_workbook(content, content_type=content_type)
    # Bước 2: Đọc cached value (data_only=True, read_only=True, keep_links=False)
    cached_sheets = _read_cached_native_sheets(content)

    effective_sample_limit = max(0, int(sample_rows_limit))
    used_table_names: set[str] = set()
    tables: list[NormalizedExcelTable] = []

    for sheet in raw_sheets:
        sheet_name: str = sheet["name"]
        all_rows: list[tuple[int, list[str]]] = [
            (sheet["header_row"], list(sheet["columns"])),
            *[(idx, list(vals)) for idx, vals in sheet["rows"]],
        ]
        native_rows_by_index = cached_sheets.get(sheet_name, {})

        header_pos = _detect_header_position(all_rows, native_rows_by_index)
        if header_pos is None:
            logger.info("Skipping worksheet without valid header row: sheet=%s", sheet_name)
            continue

        header_row_index, raw_header_cells = all_rows[header_pos]
        _ = header_row_index
        data_rows = all_rows[header_pos + 1 :]
        if not data_rows:
            logger.info("Skipping worksheet without data rows after header: sheet=%s", sheet_name)
            continue

        # Xác định số cột thực tế có dữ liệu hoặc có header
        max_col = 0
        for idx, cell in enumerate(raw_header_cells, start=1):
            if cell.strip():
                max_col = max(max_col, idx)
        for row_idx, row_cells in data_rows:
            native_row = native_rows_by_index.get(row_idx, [])
            for idx, cell in enumerate(row_cells, start=1):
                native_val = native_row[idx - 1] if idx - 1 < len(native_row) else None
                if cell.strip() or native_val is not None:
                    max_col = max(max_col, idx)

        if max_col == 0:
            logger.info("Skipping worksheet with zero active columns: sheet=%s", sheet_name)
            continue

        table_name = normalize_table_name(sheet_name, used_table_names)
        used_col_names: set[str] = set()
        col_names_and_originals: list[tuple[str, str]] = []
        for col_idx in range(1, max_col + 1):
            raw_header = (
                raw_header_cells[col_idx - 1] if col_idx - 1 < len(raw_header_cells) else ""
            )
            col_names_and_originals.append(
                normalize_column_name(raw_header, col_idx, used_col_names)
            )

        # Thu thập mẫu dữ liệu từng cột và lọc bỏ các dòng mà toàn bộ ô sau khi tính công thức đều rỗng
        row_count = len(data_rows)
        column_samples: list[list[_CellSample]] = [[] for _ in range(max_col)]
        for row_idx, raw_cells in data_rows:
            native_row = native_rows_by_index.get(row_idx, [])
            for col_offset in range(max_col):
                raw_text = raw_cells[col_offset] if col_offset < len(raw_cells) else ""
                native_val = native_row[col_offset] if col_offset < len(native_row) else None
                is_formula = raw_text.strip().startswith("=")
                column_samples[col_offset].append(
                    _CellSample(
                        raw_text=raw_text,
                        native_value=native_val,
                        is_formula=is_formula,
                    )
                )

        columns_meta: list[NormalizedColumnSchema] = []
        arrow_fields: list[pa.Field] = []
        arrow_arrays: list[pa.Array] = []
        typed_columns_data: list[list[Any]] = []
        table_has_formula = False

        for col_offset, (col_name, original_name) in enumerate(col_names_and_originals):
            data_type, typed_values, nullable, col_has_formula = _infer_column_type_and_values(
                column_samples[col_offset]
            )
            if col_has_formula:
                table_has_formula = True
            description = _build_column_description(
                original_name,
                data_type,
                typed_values,
                has_formula_values=col_has_formula,
            )
            is_free_text = classify_free_text_column(
                name=col_name,
                original_name=original_name,
                data_type=data_type,
                values=typed_values,
            )
            columns_meta.append(
                NormalizedColumnSchema(
                    name=col_name,
                    original_name=original_name,
                    data_type=data_type,
                    nullable=nullable,
                    description=description,
                    has_formula_values=col_has_formula,
                    is_free_text=is_free_text,
                )
            )
            pa_type = _arrow_type_for(data_type)
            arrow_fields.append(pa.field(col_name, pa_type, nullable=nullable))
            arrow_arrays.append(pa.array(typed_values, type=pa_type))
            typed_columns_data.append(typed_values)

        schema = pa.schema(arrow_fields)
        pa_table = pa.Table.from_arrays(arrow_arrays, schema=schema)
        parquet_buffer = BytesIO()
        pq.write_table(pa_table, parquet_buffer, compression=compression)

        sample_rows: list[dict[str, Any]] = []
        for r_idx in range(min(row_count, effective_sample_limit)):
            sample_row: dict[str, Any] = {}
            for c_idx, col_schema in enumerate(columns_meta):
                sample_row[col_schema.name] = _format_sample_scalar(
                    typed_columns_data[c_idx][r_idx],
                    max_chars=_MAX_SAMPLE_CELL_CHARS,
                )
            sample_rows.append(sample_row)

        logger.info(
            "Normalized worksheet to Parquet table: table=%s rows=%d cols=%d",
            table_name,
            row_count,
            len(columns_meta),
        )
        tables.append(
            NormalizedExcelTable(
                table_name=table_name,
                sheet_name=sheet_name,
                parquet_bytes=parquet_buffer.getvalue(),
                row_count=row_count,
                columns=tuple(columns_meta),
                sample_rows=tuple(sample_rows),
                has_formula_values=table_has_formula,
            )
        )

    return tables


def is_sensitive_column_name(
    name: str,
    original_name: str = "",
    patterns: Sequence[str] | None = None,
) -> bool:
    """Kiểm tra tên cột có khớp danh sách từ khóa nhạy cảm (`EXCEL_SENSITIVE_COLUMN_PATTERNS`) hay không."""
    active_patterns = (
        patterns
        if patterns is not None
        else getattr(settings, "excel_sensitive_column_patterns", ())
    )
    if isinstance(active_patterns, str):
        active_patterns = [p.strip().lower() for p in active_patterns.split(",") if p.strip()]

    norm_name = _NON_ALNUM_RE.sub("_", _strip_accents(name or "").lower()).strip("_")
    norm_orig = _NON_ALNUM_RE.sub("_", _strip_accents(original_name or "").lower()).strip("_")
    name_tokens = set(norm_name.split("_")) if norm_name else set()
    orig_tokens = set(norm_orig.split("_")) if norm_orig else set()

    for raw_pattern in active_patterns:
        pat = _NON_ALNUM_RE.sub("_", _strip_accents(str(raw_pattern)).lower()).strip("_")
        if not pat:
            continue
        if "_" in pat:
            if pat in norm_name or pat in norm_orig:
                return True
        else:
            if (
                pat in name_tokens
                or pat in orig_tokens
                or pat in norm_name
                or pat in norm_orig
            ):
                return True
    return False


def classify_free_text_column(
    *,
    name: str,
    original_name: str,
    data_type: ColumnDataType,
    values: Sequence[Any],
    sensitive_patterns: Sequence[str] | None = None,
) -> bool:
    """Phân loại cột Excel có phải văn bản tự do (`is_free_text`) để embed lên Qdrant hay không."""
    if data_type != "VARCHAR":
        return False
    if is_sensitive_column_name(name, original_name, sensitive_patterns):
        return False

    non_empty = [
        str(val).strip()
        for val in values
        if val is not None and str(val).strip()
    ]
    if not non_empty:
        return False

    total = len(non_empty)
    avg_chars = sum(len(s) for s in non_empty) / total
    distinct_count = len(set(non_empty))
    unique_ratio = distinct_count / total
    no_space_ratio = sum(1 for s in non_empty if " " not in s) / total
    word_counts = [len(s.split()) for s in non_empty]
    multiword_ratio = (
        sum(1 for wc in word_counts if wc >= FREE_TEXT_MIN_WORDS_PER_CELL) / total
    )

    # Loại cột mã / ID (chuỗi ngắn không khoảng trắng hoặc tỷ lệ duy nhất cao kèm từ khóa mã/ID)
    if no_space_ratio >= ID_CODE_MIN_UNIQUE_RATIO and avg_chars <= ID_CODE_MAX_AVG_CHARS:
        return False
    name_tokens = set(
        _NON_ALNUM_RE.sub("_", _strip_accents(f"{name}_{original_name}").lower())
        .strip("_")
        .split("_")
    )
    if (
        unique_ratio >= ID_CODE_MIN_UNIQUE_RATIO
        and avg_chars <= ID_CODE_MAX_AVG_CHARS
        and bool(name_tokens & _ID_COLUMN_NAME_TOKENS)
    ):
        return False

    # Loại cột nhãn phân loại ngắn (ít giá trị distinct lặp lại nhiều hoặc câu rất ngắn)
    if (
        avg_chars < FREE_TEXT_MIN_AVG_CHARS
        and distinct_count <= SHORT_CATEGORY_MAX_DISTINCT
        and (
            unique_ratio <= SHORT_CATEGORY_MAX_UNIQUE_RATIO
            or max(word_counts) < FREE_TEXT_MIN_WORDS_PER_CELL
        )
    ):
        return False

    return bool(
        avg_chars >= FREE_TEXT_MIN_AVG_CHARS
        or multiword_ratio >= FREE_TEXT_MIN_MULTIWORD_RATIO
    )


def extract_free_text_row_entries(
    content: bytes,
    *,
    content_type: str | None = None,
    sensitive_patterns: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Trích xuất các dòng chứa giá trị cột `is_free_text=True` phục vụ selective embedding."""
    raw_sheets = read_workbook(content, content_type=content_type)
    cached_sheets = _read_cached_native_sheets(content)
    entries: list[dict[str, Any]] = []

    for sheet in raw_sheets:
        sheet_name: str = sheet["name"]
        all_rows: list[tuple[int, list[str]]] = [
            (sheet["header_row"], list(sheet["columns"])),
            *[(idx, list(vals)) for idx, vals in sheet["rows"]],
        ]
        native_rows_by_index = cached_sheets.get(sheet_name, {})
        header_pos = _detect_header_position(all_rows, native_rows_by_index)
        if header_pos is None:
            continue
        _header_row_index, raw_header_cells = all_rows[header_pos]
        data_rows = all_rows[header_pos + 1 :]
        if not data_rows:
            continue

        max_col = 0
        for idx, cell in enumerate(raw_header_cells, start=1):
            if cell.strip():
                max_col = max(max_col, idx)
        for row_idx, row_cells in data_rows:
            native_row = native_rows_by_index.get(row_idx, [])
            for idx, cell in enumerate(row_cells, start=1):
                native_val = native_row[idx - 1] if idx - 1 < len(native_row) else None
                if cell.strip() or native_val is not None:
                    max_col = max(max_col, idx)
        if max_col == 0:
            continue

        used_col_names: set[str] = set()
        col_names_and_originals: list[tuple[str, str]] = []
        for col_idx in range(1, max_col + 1):
            raw_header = (
                raw_header_cells[col_idx - 1] if col_idx - 1 < len(raw_header_cells) else ""
            )
            col_names_and_originals.append(
                normalize_column_name(raw_header, col_idx, used_col_names)
            )

        column_samples: list[list[_CellSample]] = [[] for _ in range(max_col)]
        for row_idx, raw_cells in data_rows:
            native_row = native_rows_by_index.get(row_idx, [])
            for col_offset in range(max_col):
                raw_text = raw_cells[col_offset] if col_offset < len(raw_cells) else ""
                native_val = native_row[col_offset] if col_offset < len(native_row) else None
                is_formula = raw_text.strip().startswith("=")
                column_samples[col_offset].append(
                    _CellSample(
                        raw_text=raw_text,
                        native_value=native_val,
                        is_formula=is_formula,
                    )
                )

        typed_columns_data: list[list[Any]] = []
        free_text_col_indices: list[int] = []
        id_col_index: int | None = None

        for col_offset, (col_name, original_name) in enumerate(col_names_and_originals):
            data_type, typed_values, _nullable, _col_has_formula = _infer_column_type_and_values(
                column_samples[col_offset]
            )
            typed_columns_data.append(typed_values)
            is_ft = classify_free_text_column(
                name=col_name,
                original_name=original_name,
                data_type=data_type,
                values=typed_values,
                sensitive_patterns=sensitive_patterns,
            )
            if is_ft:
                free_text_col_indices.append(col_offset)
            elif id_col_index is None and not is_sensitive_column_name(
                col_name, original_name, sensitive_patterns
            ):
                col_tokens = set(col_name.split("_"))
                if col_tokens & _ID_COLUMN_NAME_TOKENS or col_offset == 0:
                    id_col_index = col_offset

        if not free_text_col_indices:
            continue

        for r_idx, (excel_row_idx, _raw_cells) in enumerate(data_rows):
            free_text_fields: list[tuple[str, str]] = []
            for ft_col_idx in free_text_col_indices:
                val = typed_columns_data[ft_col_idx][r_idx]
                if val is None:
                    continue
                text_val = str(val).strip()
                if not text_val:
                    continue
                _col_name, orig_name = col_names_and_originals[ft_col_idx]
                free_text_fields.append((orig_name, text_val))
            if not free_text_fields:
                continue

            identifier: tuple[str, str] | None = None
            if id_col_index is not None:
                id_val = typed_columns_data[id_col_index][r_idx]
                if id_val is not None and str(id_val).strip():
                    _id_name, id_orig_name = col_names_and_originals[id_col_index]
                    identifier = (id_orig_name, str(id_val).strip())

            entries.append(
                {
                    "sheet_name": sheet_name,
                    "row_index": excel_row_idx,
                    "identifier": identifier,
                    "free_text_fields": free_text_fields,
                }
            )

    return entries
