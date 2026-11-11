"""Technical indexing steps (parse → split → embed → vector records) dùng bởi ingestion.

Module này không biết document lifecycle (status, version, activate): Documents chỉ gọi
các bước kỹ thuật này và tự điều phối trạng thái.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, BinaryIO, ContextManager

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.rag.embeddings import get_embeddings
from app.rag.vector_index import VectorRecord, chunk_point_id


def parse_and_split(
    open_source: Callable[[], ContextManager[BinaryIO]],
    *,
    suffix: str,
    loader: Callable[[str | Path], list[Document]],
    splitter: Callable[[list[Document]], list[Document]],
) -> list[Document]:
    """Copy raw bytes to a temp file with the original suffix, then load and split."""
    with tempfile.TemporaryDirectory(prefix="rag-ingestion-") as directory:
        parse_path = Path(directory) / f"source{suffix}"
        with open_source() as source, parse_path.open("wb") as target:
            shutil.copyfileobj(source, target)
        documents = loader(parse_path)
        return splitter(documents)


def embed_chunks(chunks: Sequence[Document], embeddings: Embeddings | None) -> list[Any]:
    """Embed chunk texts; the provider is resolved lazily when none is injected."""
    resolved = embeddings if embeddings is not None else get_embeddings()
    return resolved.embed_documents([chunk.page_content for chunk in chunks])


def build_vector_records(
    *,
    document_id: str,
    version_id: str,
    file_name: str,
    chunks: Sequence[Document],
    vectors: Sequence[Sequence[float]],
) -> list[VectorRecord]:
    return [
        VectorRecord(
            point_id=chunk_point_id(version_id, chunk_index),
            document_id=document_id,
            version_id=version_id,
            chunk_index=chunk_index,
            file_name=file_name,
            chunk_text=chunk.page_content,
            page=(
                None
                if chunk.metadata.get("page") is None
                else int(chunk.metadata["page"])
            ),
            vector=tuple(vector),
            sheet_name=chunk.metadata.get("sheet_name"),
            row_index=chunk.metadata.get("row_index"),
        )
        for chunk_index, (chunk, vector) in enumerate(
            zip(chunks, vectors, strict=True)
        )
    ]
