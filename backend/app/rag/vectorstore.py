"""Vector store PostgreSQL + pgvector qua integration của LangChain.

Mỗi embedding model dùng một table riêng (`rag_chunks_<model>`) để không trộn
vector giữa các model — phục vụ benchmark ở phase sau.

Phase 2 chỉ add/update document và kiểm tra dữ liệu; KHÔNG implement retrieval
pipeline (retriever/prompt/LLM).
"""

import re
import uuid
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres import PGVectorStore
from sqlalchemy import text

from app.config import settings
from app.db import get_engine, get_sync_engine, table_exists
from app.rag.embeddings import get_embeddings

_DIMENSION_PROBE = "rag-demo dimension probe"
_TABLE_PREFIX = "rag_chunks"
_METADATA_JSON_COLUMN = "langchain_metadata"


def table_name_for_embedding_model(model: str) -> str:
    """Sinh tên table riêng cho một embedding model, ví dụ `rag_chunks_gemini_embedding_001`."""
    safe_model = re.sub(r"[^0-9a-zA-Z]+", "_", model).strip("_").lower()
    return f"{_TABLE_PREFIX}_{safe_model}"


def get_embedding_dimension(embeddings: Embeddings) -> int:
    """Lấy số chiều vector bằng cách embed một chuỗi probe ngắn.

    Chỉ gọi 1 lần cho mỗi table lúc khởi tạo; không hard-code dimension.
    """
    return len(embeddings.embed_query(_DIMENSION_PROBE))


def get_vectorstore(
    embeddings: Embeddings | None = None,
    table_name: str | None = None,
    *,
    overwrite: bool = False,
) -> PGVectorStore:
    """Trả về `PGVectorStore` đã sẵn sàng, tự tạo table nếu chưa có.

    Args:
        embeddings: Embeddings object; mặc định dùng `get_embeddings()`.
        table_name: Tên table; mặc định suy ra từ `settings.embedding_model`.
        overwrite: Nếu True, drop và tạo lại table (dùng cho test/benchmark).

    Returns:
        `PGVectorStore` trỏ tới table tương ứng.
    """
    resolved_embeddings = embeddings if embeddings is not None else get_embeddings()
    resolved_table = table_name or table_name_for_embedding_model(settings.embedding_model)
    engine = get_engine()

    if overwrite or not table_exists(resolved_table):
        engine.init_vectorstore_table(
            table_name=resolved_table,
            vector_size=get_embedding_dimension(resolved_embeddings),
            overwrite_existing=overwrite,
        )

    return PGVectorStore.create_sync(
        engine=engine,
        embedding_service=resolved_embeddings,
        table_name=resolved_table,
    )


def add_document(
    chunks: list[Document],
    *,
    document_id: str | None = None,
    embeddings: Embeddings | None = None,
    table_name: str | None = None,
) -> str:
    """Add/update toàn bộ chunk của một document vào vector store.

    Gán metadata tối thiểu `document_id` và `chunk_index`; giữ `file_name` và
    `page` có sẵn từ loader. Dùng id deterministic nên add lại cùng
    `document_id` sẽ update các chunk có cùng `chunk_index`.

    Args:
        chunks: Danh sách chunk (đã split) của một document.
        document_id: ID document; nếu None sẽ sinh UUID mới.
        embeddings: Embeddings object; mặc định dùng `get_embeddings()`.
        table_name: Tên table; mặc định suy ra từ `settings.embedding_model`.

    Returns:
        `document_id` đã dùng.

    Raises:
        ValueError: Nếu `chunks` rỗng.
    """
    if not chunks:
        raise ValueError("Cần ít nhất một chunk để add_document.")

    resolved_document_id = document_id or str(uuid.uuid4())
    store = get_vectorstore(embeddings=embeddings, table_name=table_name)

    ids: list[str] = []
    for chunk_index, chunk in enumerate(chunks):
        chunk.metadata["document_id"] = resolved_document_id
        chunk.metadata["chunk_index"] = chunk_index
        chunk.metadata.setdefault("file_name", _file_name_from_metadata(chunk))
        ids.append(
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{resolved_document_id}:{chunk_index}"))
        )

    store.add_documents(chunks, ids=ids)
    return resolved_document_id


def _file_name_from_metadata(document: Document) -> str:
    """Suy ra `file_name` từ metadata `source` nếu loader chưa set."""
    source = document.metadata.get("source")
    if source:
        return Path(str(source)).name
    return "unknown"


def _resolve_table_name(table_name: str | None) -> str:
    """Tên table dùng cho thao tác document: tham số nếu có, ngược lại suy từ embedding model."""
    return table_name or table_name_for_embedding_model(settings.embedding_model)


def delete_document(document_id: str, *, table_name: str | None = None) -> int:
    """Xóa toàn bộ chunk của một `document_id` khỏi vector table.

    Dùng cho DELETE document và cho re-index (không để lại chunk cũ).
    Trả về số row đã xóa; 0 nếu table chưa tồn tại hoặc không có chunk nào.
    """
    resolved_table = _resolve_table_name(table_name)
    if not table_exists(resolved_table):
        return 0

    statement = text(
        f'DELETE FROM "{resolved_table}" '
        f"WHERE {_METADATA_JSON_COLUMN} ->> 'document_id' = :document_id"
    )
    with get_sync_engine().begin() as connection:
        result = connection.execute(statement, {"document_id": document_id})
        return int(result.rowcount or 0)


def list_documents(*, table_name: str | None = None) -> list[dict]:
    """Liệt kê document đã index (gom theo `document_id`) kèm số chunk.

    Returns:
        list[dict] gồm `document_id`, `file_name`, `chunk_count`.
    """
    resolved_table = _resolve_table_name(table_name)
    if not table_exists(resolved_table):
        return []

    statement = text(
        f"SELECT {_METADATA_JSON_COLUMN} ->> 'document_id' AS document_id, "
        f"{_METADATA_JSON_COLUMN} ->> 'file_name' AS file_name, "
        f"count(*) AS chunk_count "
        f'FROM "{resolved_table}" GROUP BY 1, 2 ORDER BY 2, 1'
    )
    with get_sync_engine().connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [
        {
            "document_id": row["document_id"],
            "file_name": row["file_name"],
            "chunk_count": int(row["chunk_count"]),
        }
        for row in rows
    ]
