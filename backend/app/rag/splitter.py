"""Chunk `list[Document]` thành các đoạn nhỏ bằng text splitter của LangChain.

Hỗ trợ RecursiveCharacterTextSplitter thông thường và Parent-Child (Hierarchical) Chunking.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.shared.config import settings


def split_parent_child(
    documents: list[Document],
    parent_size: int | None = None,
    parent_overlap: int | None = None,
    child_size: int | None = None,
    child_overlap: int | None = None,
) -> list[Document]:
    """Chia documents theo chiến lược Parent-Child (Hierarchical Chunking).

    - Parent chunk: chứa ngữ cảnh rộng hơn (dùng để cung cấp cho LLM).
    - Child chunk: chứa ngữ cảnh tập trung hơn (dùng để embedding và tìm kiếm vector).
    Mỗi child chunk sẽ lưu tham chiếu `parent_id` và `parent_text` trong metadata.
    """
    p_size = parent_size if parent_size is not None else getattr(settings, "parent_chunk_size", 1200)
    p_overlap = parent_overlap if parent_overlap is not None else getattr(settings, "parent_chunk_overlap", 100)
    c_size = child_size if child_size is not None else getattr(settings, "child_chunk_size", 300)
    c_overlap = child_overlap if child_overlap is not None else getattr(settings, "child_chunk_overlap", 30)

    if p_size <= p_overlap:
        raise ValueError(f"parent_size ({p_size}) phải lớn hơn parent_overlap ({p_overlap}).")
    if c_size <= c_overlap:
        raise ValueError(f"child_size ({c_size}) phải lớn hơn child_overlap ({c_overlap}).")
    if c_size >= p_size:
        raise ValueError(f"child_size ({c_size}) phải nhỏ hơn parent_size ({p_size}).")

    parent_splitter = RecursiveCharacterTextSplitter(chunk_size=p_size, chunk_overlap=p_overlap)
    child_splitter = RecursiveCharacterTextSplitter(chunk_size=c_size, chunk_overlap=c_overlap)

    parent_docs = parent_splitter.split_documents(documents)
    child_docs: list[Document] = []

    for parent_idx, parent_doc in enumerate(parent_docs):
        version_id = str(parent_doc.metadata.get("version_id", ""))
        doc_id = str(parent_doc.metadata.get("document_id", ""))
        parent_id = str(uuid5(NAMESPACE_URL, f"{doc_id}:{version_id}:parent:{parent_idx}"))
        parent_text = parent_doc.page_content

        children = child_splitter.split_documents([parent_doc])
        for child_idx, child in enumerate(children):
            metadata = dict(child.metadata)
            metadata["parent_id"] = parent_id
            metadata["parent_text"] = parent_text
            metadata["parent_index"] = parent_idx
            metadata["child_index"] = child_idx
            child_docs.append(Document(page_content=child.page_content, metadata=metadata))

    return child_docs


def split_documents(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    parent_child: bool | None = None,
) -> list[Document]:
    """Chia documents thành nhiều chunk nhỏ hơn.

    Args:
        documents: Các Document đã load từ loader.
        chunk_size: Số ký tự mỗi chunk. Mặc định lấy từ `settings`.
        chunk_overlap: Số ký tự overlap giữa 2 chunk liền nhau. Mặc định lấy từ `settings`.
        parent_child: Bật Parent-Child chunking. Mặc định đọc từ settings.parent_child_enabled.

    Returns:
        Danh sách chunk dưới dạng `Document`.
    """
    is_parent_child = (
        parent_child
        if parent_child is not None
        else getattr(settings, "parent_child_enabled", False)
    )
    if is_parent_child and chunk_size is None and chunk_overlap is None:
        return split_parent_child(documents)

    size = chunk_size if chunk_size is not None else settings.chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap
    if size <= overlap:
        raise ValueError(
            f"chunk_size ({size}) phải lớn hơn chunk_overlap ({overlap})."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
    )
    return splitter.split_documents(documents)
