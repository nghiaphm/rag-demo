"""Chunk `list[Document]` thành các đoạn nhỏ bằng text splitter của LangChain.

Chiến lược mặc định của V1 là `RecursiveCharacterTextSplitter`.
Phase 1 chỉ split text; KHÔNG embedding và KHÔNG lưu database.
"""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.shared.config import settings


def split_documents(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Document]:
    """Chia documents thành nhiều chunk nhỏ hơn.

    Args:
        documents: Các Document đã load từ loader.
        chunk_size: Số ký tự mỗi chunk. Mặc định lấy từ `settings`.
        chunk_overlap: Số ký tự overlap giữa 2 chunk liền nhau. Mặc định lấy từ `settings`.

    Returns:
        Danh sách chunk dưới dạng `Document`; metadata của Document gốc
        được giữ nguyên trên từng chunk.

    Raises:
        ValueError: Nếu `chunk_size` không lớn hơn `chunk_overlap`.
    """
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
