"""Bounded, read-only XLSX validation/parsing shared by ingestion and versioned previews."""

from datetime import date, datetime, time
from io import BytesIO
import math
from zipfile import ZipFile

from openpyxl import load_workbook

MAX_XLSX_BYTES = 10 * 1024 * 1024
MAX_XLSX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_SHEETS = 50
MAX_ROWS = 20_000
MAX_COLUMNS = 200
MAX_CELLS = 250_000
MAX_CELL_CHARS = 32_767
XLSX_MIME_TYPES = frozenset({
    "", "application/octet-stream", "application/zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})


class WorkbookError(ValueError):
    """Safe messages describing rejected workbook input."""


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        raise WorkbookError("Workbook chứa giá trị số không hợp lệ.")
    text = str(value)
    if len(text) > MAX_CELL_CHARS:
        raise WorkbookError("Ô Excel vượt quá giới hạn 32767 ký tự.")
    return text


def read_workbook(content: bytes, *, content_type: str | None = None) -> list[dict]:
    if (content_type or "").split(";", 1)[0].strip().lower() not in XLSX_MIME_TYPES:
        raise WorkbookError("MIME không phù hợp với file XLSX.")
    if not content or len(content) > MAX_XLSX_BYTES:
        raise WorkbookError("File XLSX phải không rỗng và không quá 10 MiB.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            names = {entry.filename.lower() for entry in entries}
            if len(entries) > 5000 or sum(entry.file_size for entry in entries) > MAX_XLSX_EXPANDED_BYTES:
                raise WorkbookError("Workbook giải nén vượt giới hạn an toàn.")
            if "[content_types].xml" not in names or "xl/workbook.xml" not in names:
                raise WorkbookError("Nội dung không phải workbook XLSX hợp lệ.")
            if any("vbaproject" in name or "/macrosheets/" in name for name in names):
                raise WorkbookError("Không hỗ trợ workbook chứa macro.")
            if b"macroenabled" in archive.read("[Content_Types].xml").lower():
                raise WorkbookError("Không hỗ trợ workbook chứa macro.")
        # Formulas remain literal strings. No calculation, macros or external link resolution.
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
        try:
            if len(workbook.worksheets) > MAX_SHEETS:
                raise WorkbookError("Workbook vượt giới hạn 50 sheet.")
            sheets = []
            cells = 0
            for sheet in workbook.worksheets:
                if not sheet.title or len(sheet.title) > 31:
                    raise WorkbookError("Tên sheet phải có từ 1 đến 31 ký tự.")
                if (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLUMNS:
                    raise WorkbookError("Sheet vượt giới hạn 20000 hàng hoặc 200 cột.")
                rows = []
                for index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                    if index > MAX_ROWS or len(row) > MAX_COLUMNS:
                        raise WorkbookError("Kích thước sheet không hợp lệ.")
                    cells += len(row)
                    if cells > MAX_CELLS:
                        raise WorkbookError("Workbook vượt giới hạn 250000 ô.")
                    values = [_cell_text(value) for value in row]
                    if any(value.strip() for value in values):
                        rows.append((index, values))
                if rows:
                    header_index, columns = rows[0]
                    sheets.append({"name": sheet.title, "columns": columns,
                                   "header_row": header_index, "rows": rows[1:]})
            if not sheets:
                raise WorkbookError("Workbook rỗng, không có dữ liệu để index.")
            return sheets
        finally:
            workbook.close()
    except WorkbookError:
        raise
    except Exception as exc:
        raise WorkbookError("Không thể đọc workbook XLSX; file lỗi, được mã hóa hoặc sai định dạng.") from exc
