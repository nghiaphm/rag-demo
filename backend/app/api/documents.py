"""Endpoints quản lý document: upload, list, delete.

API layer chỉ validate request/response và gọi service (app.rag.pipeline);
không tự implement loader/splitter/embedding/retrieval/generation.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import PROJECT_ROOT, settings
from app.rag.loader import SUPPORTED_EXTENSIONS
from app.rag.pipeline import delete_document, index_document, list_documents
from app.schemas import DeleteDocumentResponse, DocumentIndexInfo, DocumentInfo

router = APIRouter(prefix="/documents", tags=["documents"])


def _documents_dir() -> Path:
    """Thư mục lưu file upload (absolute), tính từ project root nếu là path tương đối."""
    documents_dir = Path(settings.documents_dir)
    if not documents_dir.is_absolute():
        documents_dir = PROJECT_ROOT / documents_dir
    return documents_dir


@router.post("/upload", response_model=DocumentIndexInfo, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> DocumentIndexInfo:
    """Upload file, lưu vào `documents_dir` và index vào vector store."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Thiếu tên file.")

    file_name = Path(file.filename).name
    suffix = Path(file_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng '{suffix}' không được hỗ trợ. Hỗ trợ: {supported}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File rỗng.")

    documents_dir = _documents_dir()
    documents_dir.mkdir(parents=True, exist_ok=True)
    target_path = documents_dir / file_name
    target_path.write_bytes(content)

    document_id = f"upload-{uuid.uuid5(uuid.NAMESPACE_URL, file_name)}"
    try:
        result = index_document(target_path, document_id=document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DocumentIndexInfo(**result)


@router.get("", response_model=list[DocumentInfo])
def get_documents() -> list[DocumentInfo]:
    """Danh sách các document đã index."""
    return [DocumentInfo(**item) for item in list_documents()]


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
def remove_document(document_id: str) -> DeleteDocumentResponse:
    """Xóa document và toàn bộ chunk/vector liên quan theo `document_id`."""
    deleted_chunks = delete_document(document_id)
    if deleted_chunks == 0:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy document: {document_id}")
    return DeleteDocumentResponse(document_id=document_id, deleted_chunks=deleted_chunks)
