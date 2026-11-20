"""Row-text projection của workbook cho RAG ingestion."""

from langchain_core.documents import Document

from app.documents.excel.tabular import extract_free_text_row_entries
from app.documents.excel.validation import WorkbookError, read_workbook
from app.shared.config import settings

MAX_INGEST_CHARS = 16 * 1024 * 1024
MAX_ROW_CHARS = 64 * 1024


def workbook_documents(content: bytes) -> list[Document]:
    if getattr(settings, "excel_text_only_embedding_enabled", False):
        documents: list[Document] = []
        characters = 0
        for entry in extract_free_text_row_entries(content):
            lines = [
                f"Sheet: {entry['sheet_name']}",
                f"Row: {entry['row_index']}",
            ]
            identifier = entry.get("identifier")
            if identifier is not None:
                id_col, id_val = identifier
                lines.append(f"{id_col}: {id_val}")
            for col_name, text_val in entry["free_text_fields"]:
                lines.append(f"{col_name}: {text_val}")
            text = "\n".join(lines)
            characters += len(text)
            if len(text) > MAX_ROW_CHARS or characters > MAX_INGEST_CHARS:
                raise WorkbookError(
                    "Nội dung bảng vượt giới hạn 65536 ký tự mỗi hàng hoặc 16777216 ký tự sau parse."
                )
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "sheet_name": entry["sheet_name"],
                        "row_index": entry["row_index"],
                    },
                )
            )
        return documents

    documents = []
    characters = 0
    for sheet in read_workbook(content):
        columns = sheet["columns"]
        rows = sheet["rows"] or [(sheet["header_row"], columns)]
        for index, values in rows:
            lines = [f"{columns[i] if i < len(columns) and columns[i] else f'Column {i + 1}'}: {value}"
                     for i, value in enumerate(values)]
            text = f"Sheet: {sheet['name']}\nRow: {index}\n" + "\n".join(lines)
            characters += len(text)
            if len(text) > MAX_ROW_CHARS or characters > MAX_INGEST_CHARS:
                raise WorkbookError("Nội dung bảng vượt giới hạn 65536 ký tự mỗi hàng hoặc 16777216 ký tự sau parse.")
            documents.append(Document(page_content=text,
                                      metadata={"sheet_name": sheet["name"], "row_index": index}))
    return documents
