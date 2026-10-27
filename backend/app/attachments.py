"""Resolve immutable document versions without changing session retrieval scope."""

from pathlib import Path

from app.attachment_models import MessageAttachment
from app.document_models import DocumentStatus
from app.document_repository import RepositoryNotFoundError
from app.excel import MAX_XLSX_BYTES, workbook_preview


class AttachmentUnavailableError(ValueError):
    def __init__(self, message="Attachment không còn sẵn sàng.", status=409):
        super().__init__(message)
        self.status = status


def resolve_version(repository, document_id, version_id):
    try:
        document = repository.get_document(document_id)
        version = repository.get_version(version_id)
    except RepositoryNotFoundError as exc:
        raise AttachmentUnavailableError("Không tìm thấy phiên bản tài liệu.", 404) from exc
    if document.status == DocumentStatus.DELETED or document.deleted_at is not None:
        raise AttachmentUnavailableError("Tài liệu đã bị xóa khỏi thư viện.", 410)
    if version.document_id != document.document_id:
        raise AttachmentUnavailableError("Phiên bản không thuộc tài liệu này.", 404)
    return version


def resolve_attachments(repository, references):
    attachments = []
    for reference in references:
        version = resolve_version(repository, reference.document_id, reference.version_id)
        if version.status != DocumentStatus.INDEXED:
            raise AttachmentUnavailableError("Tài liệu chưa được index thành công.")
        attachments.append(MessageAttachment(document_id=version.document_id, version_id=version.version_id,
                                             file_name=version.file_name))
    return attachments


def preview_version(repository, storage, document_id, version_id):
    version = resolve_version(repository, document_id, version_id)
    if not version.storage_key:
        raise AttachmentUnavailableError("Phiên bản không có file gốc.", 404)
    result = {"document_id": document_id, "version_id": version_id, "file_name": version.file_name,
              "kind": "unsupported", "text": None, "sheets": [], "truncated": False}
    suffix = Path(version.file_name).suffix.lower()
    if suffix not in {".txt", ".md", ".markdown", ".xlsx"}:
        return result
    limit = MAX_XLSX_BYTES if suffix == ".xlsx" else 256 * 1024
    with storage.open(version.storage_key) as stream:
        content = stream.read(limit + 1)
    if suffix == ".xlsx":
        result.update(workbook_preview(content))
    else:
        truncated = len(content) > limit
        raw = content[:limit]
        encoding = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
        import codecs
        decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
        try:
            text = decoder.decode(raw, final=not truncated)
        except UnicodeError as exc:
            raise AttachmentUnavailableError("Không đọc được encoding; bản xem trước hỗ trợ UTF-8/UTF-16 có BOM.", 422) from exc
        result.update(kind="text", text=text, truncated=truncated)
    return result
