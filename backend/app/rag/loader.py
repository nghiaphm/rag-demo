"""Load tài liệu nguồn thành `list[Document]` bằng loader có sẵn của LangChain.

V1 hỗ trợ tối thiểu: PDF (.pdf), Markdown (.md/.markdown) và text (.txt).
Phase 1 chỉ load text; KHÔNG embedding và KHÔNG lưu database.
"""

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredExcelLoader
from langchain_core.documents import Document
import networkx as nx
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".md", ".markdown", ".txt", ".xlsx"})


def load_document(file_path: str | Path) -> list[Document]:
    """Load một file thành `list[Document]` dựa theo phần mở rộng.

    Args:
        file_path: Đường dẫn tới file PDF, Markdown hoặc TXT.

    Returns:
        Danh sách `Document`. Mỗi Document có metadata tối thiểu:
        `file_name`, `source`, và `page` nếu loader cung cấp được.

    Raises:
        FileNotFoundError: Nếu file không tồn tại.
        ValueError: Nếu phần mở rộng không được hỗ trợ.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file: {path}")

    documents = _load(path)
    _enrich_metadata(documents, path)
    return documents


def _load(path: Path) -> list[Document]:
    """Chọn loader LangChain phù hợp với phần mở rộng của file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return PyPDFLoader(str(path), mode="page").load()
    if suffix == ".xlsx":
        return UnstructuredExcelLoader(str(path), mode="elements").load()
    if suffix in {".md", ".markdown", ".txt"}:
        return _load_text(path)

    supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
    raise ValueError(f"Định dạng '{suffix}' chưa được hỗ trợ. Hỗ trợ: {supported}")


def _load_text(path: Path) -> list[Document]:
    """Load file text với UTF-8 là mặc định.

    `autodetect_encoding` của chardet có thể đoán sai file UTF-8 ngắn (đặc biệt
    tiếng Việt) và tạo mojibake, nên ưu tiên UTF-8; chỉ fallback autodetect khi
    file thực sự không phải UTF-8.
    """
    # Markdown xử lý như plain text ở V1 để tránh dependency nặng `unstructured`.
    try:
        return TextLoader(str(path), encoding="utf-8").load()
    except UnicodeDecodeError:
        return TextLoader(str(path), autodetect_encoding=True).load()


def _enrich_metadata(documents: list[Document], path: Path) -> None:
    """Chuẩn hóa metadata nguồn: luôn có `file_name` và `source`."""
    for document in documents:
        document.metadata["file_name"] = path.name
        document.metadata["source"] = str(path)
