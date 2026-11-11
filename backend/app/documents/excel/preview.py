"""Bounded workbook preview cho Documents API và message attachments."""

from app.documents.excel.validation import read_workbook


def workbook_preview(content: bytes) -> dict:
    sheets = read_workbook(content)
    budget = 256 * 1024
    remaining_rows = 200
    previews = []
    for sheet in sheets:
        truncated = len(sheet["rows"]) > min(50, remaining_rows) or len(sheet["columns"]) > 30

        def bounded(value, limit):
            nonlocal budget, truncated
            length = min(limit, budget)
            if len(value) > length:
                truncated = True
            result = value[:length]
            budget -= len(result)
            return result

        columns = [bounded(column, 200) for column in sheet["columns"][:30]]
        rows = [[bounded(value, 2000) for value in row[:30]]
                for _, row in sheet["rows"][:min(50, remaining_rows)]]
        remaining_rows -= len(rows)
        previews.append({"name": sheet["name"], "columns": columns, "rows": rows,
                         "total_rows": len(sheet["rows"]), "truncated": truncated})
    return {"kind": "excel", "sheets": previews, "truncated": any(sheet["truncated"] for sheet in previews)}
