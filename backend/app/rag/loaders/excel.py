"""Row-text projection của workbook cho RAG ingestion."""

from langchain_core.documents import Document

from app.documents.excel.validation import WorkbookError, read_workbook

MAX_INGEST_CHARS = 16 * 1024 * 1024
MAX_ROW_CHARS = 64 * 1024


def workbook_documents(content: bytes) -> list[Document]:
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
