"""Document APIs cho lifecycle MongoDB, local raw storage và Qdrant."""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.documents.repository import (
    RepositoryConflictError,
    RepositoryError,
    RepositoryNotFoundError,
)
from app.documents.service import DocumentService, DocumentSummary, create_document_service
from app.documents.ingestion import IngestionError, IngestionResult
from app.rag.loaders.files import SUPPORTED_EXTENSIONS
from app.documents.attachments import AttachmentUnavailableError, preview_version
from app.documents.ports import StorageError
from app.documents.excel.validation import MAX_XLSX_BYTES, WorkbookError, read_workbook
from app.api.schemas.chat_documents import (
    DocumentPreviewResponse,
    DeleteDocumentResponse,
    DocumentDetail,
    DocumentIndexInfo,
    DocumentInfo,
    DocumentVersionInfo,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _validated_file_name(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Thiếu tên file.")
    file_name = Path(file.filename).name
    if file_name != file.filename:
        raise HTTPException(status_code=400, detail="Tên file không hợp lệ.")
    suffix = Path(file_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng '{suffix}' không được hỗ trợ. Hỗ trợ: {supported}",
        )
    return file_name


async def _service(request: Request) -> DocumentService:
    cloud = request.app.state.cloud_connections
    if cloud.mongodb.database is None or cloud.qdrant.client is None:
        raise HTTPException(status_code=503, detail="Cloud dependencies chưa sẵn sàng.")
    return await run_in_threadpool(
        create_document_service,
        database=cloud.mongodb.database,
        qdrant_client=cloud.qdrant.client,
    )


def _index_response(result: IngestionResult) -> DocumentIndexInfo:
    return DocumentIndexInfo(
        document_id=result.document_id,
        version_id=result.version_id,
        job_id=result.job_id,
        file_name=result.file_name,
        num_chunks=result.num_chunks,
        activated=result.activated,
    )


def _version_response(version) -> DocumentVersionInfo:
    return DocumentVersionInfo(
        version_id=version.version_id,
        version=version.version,
        file_name=version.file_name,
        status=version.status,
        checksum_sha256=version.checksum_sha256,
        size_bytes=version.size_bytes,
        chunk_count=version.chunk_count,
        embedding_model=version.embedding_model,
        created_at=version.created_at,
        indexed_at=version.indexed_at,
    )


def _document_response(summary) -> DocumentInfo:
    document = summary.document
    return DocumentInfo(
        document_id=document.document_id,
        file_name=document.file_name,
        status=document.status,
        active_version_id=document.active_version_id,
        chunk_count=summary.active_version.chunk_count if summary.active_version else 0,
        version_count=summary.version_count,
        cleanup_pending=document.cleanup_pending,
        created_at=document.created_at,
        updated_at=document.updated_at,
        deleted_at=document.deleted_at,
    )


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, RepositoryNotFoundError):
        raise HTTPException(status_code=404, detail="Document không tồn tại.") from exc
    if isinstance(exc, RepositoryConflictError):
        raise HTTPException(status_code=409, detail="Document đang có xung đột trạng thái.") from exc
    if isinstance(exc, IngestionError):
        if exc.code in {"document_deleted", "active_version_missing"}:
            status_code = 409
        elif exc.code in {
            "empty_file",
            "invalid_file_name",
            "unsupported_file_type",
            "parse_failed",
        }:
            status_code = 400
        else:
            status_code = 500
        raise HTTPException(status_code=status_code, detail=exc.safe_message) from exc
    if isinstance(exc, RepositoryError):
        raise HTTPException(status_code=503, detail="Document metadata tạm thời không khả dụng.") from exc
    raise exc


async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    file_name = _validated_file_name(file)
    content = await file.read(MAX_XLSX_BYTES + 1) if Path(file_name).suffix.lower() == ".xlsx" else await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File rỗng.")
    if Path(file_name).suffix.lower() == ".xlsx":
        try:
            await run_in_threadpool(read_workbook, content, content_type=file.content_type)
        except WorkbookError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return file_name, content


@router.get("/{document_id}/versions/{version_id}/preview", response_model=DocumentPreviewResponse)
async def document_preview(document_id: UUID, version_id: UUID, request: Request):
    service = await _service(request)
    try:
        return await run_in_threadpool(preview_version, service.repository, service.storage,
                                       str(document_id), str(version_id))
    except AttachmentUnavailableError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    except WorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Không đọc được file gốc.") from exc
    except RepositoryError as exc:
        raise HTTPException(status_code=503, detail="Document metadata unavailable") from exc


@router.post("/upload", response_model=DocumentIndexInfo, status_code=201)
async def upload_document(request: Request, file: UploadFile = File(...)) -> DocumentIndexInfo:
    """Tạo document identity mới và index version đầu tiên."""
    file_name, content = await _read_upload(file)
    service = await _service(request)
    try:
        result = await run_in_threadpool(
            service.ingestion.ingest, file_name=file_name, content=content
        )
    except Exception as exc:
        _handle_error(exc)
    return _index_response(result)


@router.get("", response_model=list[DocumentInfo])
async def get_documents(
    request: Request,
    include_deleted: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DocumentInfo]:
    service = await _service(request)
    try:
        values = await run_in_threadpool(
            service.list_documents,
            include_deleted=include_deleted,
            offset=offset,
            limit=limit,
        )
    except Exception as exc:
        _handle_error(exc)
    return [_document_response(value) for value in values]


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(request: Request, document_id: UUID) -> DocumentDetail:
    service = await _service(request)
    try:
        detail = await run_in_threadpool(service.get_document, str(document_id))
    except Exception as exc:
        _handle_error(exc)
    summary = DocumentSummary(
        document=detail.document,
        active_version=next(
            (v for v in detail.versions if v.version_id == detail.document.active_version_id), None
        ),
        version_count=len(detail.versions),
    )
    base = _document_response(summary).model_dump()
    return DocumentDetail(
        **base,
        versions=[_version_response(version) for version in detail.versions],
    )


@router.put("/{document_id}", response_model=DocumentIndexInfo, status_code=201)
async def update_document(
    request: Request, document_id: UUID, file: UploadFile = File(...)
) -> DocumentIndexInfo:
    """Tạo immutable version mới từ raw file mới; active cũ được giữ nếu fail."""
    file_name, content = await _read_upload(file)
    service = await _service(request)
    try:
        result = await run_in_threadpool(
            service.update,
            str(document_id),
            file_name=file_name,
            content=content,
        )
    except Exception as exc:
        _handle_error(exc)
    return _index_response(result)


@router.post("/{document_id}/re-index", response_model=DocumentIndexInfo, status_code=201)
async def reindex_document(request: Request, document_id: UUID) -> DocumentIndexInfo:
    """Tạo version mới từ raw file của active version hiện tại."""
    service = await _service(request)
    try:
        result = await run_in_threadpool(service.reindex, str(document_id))
    except Exception as exc:
        _handle_error(exc)
    return _index_response(result)


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
async def remove_document(
    request: Request, document_id: UUID, response: Response
) -> DeleteDocumentResponse:
    """Soft-delete/unpublish, xóa Qdrant points, giữ raw files và audit history."""
    service = await _service(request)
    try:
        result = await run_in_threadpool(service.delete, str(document_id))
    except Exception as exc:
        _handle_error(exc)
    if result.cleanup_pending:
        response.status_code = 202
    return DeleteDocumentResponse(
        document_id=result.document_id,
        deleted_chunks=result.deleted_chunks,
        retained_files=result.retained_files,
        cleanup_pending=result.cleanup_pending,
    )
